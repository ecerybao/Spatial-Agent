import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from .state import SpatialAgentState
from .nodes import AgentRouting, AnswerGenerator
from .planner import PlannerAgent
from .executors import TransformationExecutor
from ..tools.google_maps import GoogleMapsClient
from ..utils.logging_utils import log_separator, log_workflow_summary, log_table, SYMBOLS

load_dotenv()


# ==================== Intent-Specific Evaluation Prompts ====================

BASE_EVALUATION_PROMPT = """You are a spatial-query evaluator. Select exactly one candidate option using the execution results.

Core principles:
1. Execution results have priority over the wording of the question.
2. Local database outputs, route summaries, computed distances, computed times, filtered place lists, and intermediate_concepts are authoritative evidence.
3. Exact option-text matches beat semantic matches. Semantic matches beat inference. Inference is only a fallback.
4. The final predicted_answer must exactly equal one candidate option whenever possible.
5. Return JSON only with keys: predicted_answer, predicted_option, confidence, reason.
6. predicted_option is zero-based.

Input sections you will receive:
- Question: original question text.
- Candidate options: JSON list of answer choices.
- Execution results: serialized local database/API/operator outputs.
"""

NEARBY_EVALUATION_PROMPT = """Nearby evaluation rules:
1. For nearest/closest questions, match each candidate option to the nearby list and choose the matched option with the smallest rank or shortest distance.
2. For second/third nearest, sort matched options by rank or distance and choose the requested ordinal item.
3. For highest/lowest rating, most/fewest reviews, price, or similar extrema, compare only candidate options that can be matched to execution results.
4. For radius questions, use only results inside the requested radius_meters. If the nearby query already applied the radius, count or compare that filtered list.
5. For opening-hours constraints, prefer filtered outputs such as open_restaurants/open_places over raw nearby lists.
6. For count questions, count records satisfying the requested type, radius, and time condition, then match the numeric count to an option.
7. Do not choose a place that appears in the nearby list but is not one of the candidate options, unless the option text contains that place name.
8. In the reason, cite the compared ranks, distances, ratings, or counts.

Example reasoning pattern:
- Options: A, B, C, D.
- Nearby ranks: A=8, B=5, C=4, D=7.
- For nearest, 4 is smallest, so choose C.
"""

ROUTING_EVALUATION_PROMPT = """Routing evaluation rules:
1. If a local route summary exists, read it directly before using any question-wording guess.
2. If the question names a specific via route, isolate that route section in the summary first; do not use a different route alternative.
3. For next-step questions, locate the referenced road/landmark after "after reaching" inside the selected route, then return the following instruction.
4. For route-distance or route-duration questions, use routes_info, total_distance_km, total_time_mins, extract_distance, or extract_duration when present.
5. For best/shortest/fastest route questions, compare route alternatives numerically. Shortest uses distance; fastest uses duration.
6. For roundabout questions, count explicit roundabout mentions or use count_in_route if available.
7. Match the chosen route name, instruction, distance, or duration to the exact candidate option text.

When a summary contains numbered alternatives, treat each numbered alternative as a separate route. A via-route name in the question must match the alternative name before extracting next steps or metrics.
"""

TRIP_EVALUATION_PROMPT = """Trip evaluation rules:
1. For fixed-order total-time questions, sum all relevant query_local_travel_time or duration outputs, plus visit durations only when the question asks total elapsed trip time or feasibility.
2. For option sequences, evaluate each candidate option as an ordered sequence. Order matters: A -> B -> C is not the same as B -> A -> C.
3. For best-order questions, choose the option whose sequence has the lowest total travel time or the optimized order returned by tsp_tw.
4. For schedule questions, compute arrival and departure times in order from the start time, travel times, and visit durations.
5. For latest-departure questions, work backward from the deadline, closing time, or required arrival time.
6. For feasibility questions, combine travel time, visit durations, opening-hours constraints, start time, and time budget.
7. Match computed times to the closest exact option. Return the option text, not only a normalized time.
8. Ignore tiny spelling differences in place names when matching, but never ignore sequence order.
"""

POI_EVALUATION_PROMPT = """POI evaluation rules:
1. For place attributes such as rating, address, opening hours, price, or type, use query_local_place/place_details outputs directly.
2. For open-at-time questions, use open_status/open_at_time/is_open_at_time_text outputs when present; otherwise inspect opening_hours text.
3. For direction questions, use bearing_to_direction output first. If only bearing is present, map it to the candidate direction set.
4. For distance or pairwise comparison questions, use computed coordinates and distances. For closest pair, choose the smallest distance; for farthest pair, choose the largest distance.
5. For "between A and B" questions, prefer evidence showing the candidate lies between or closest to the midpoint/route between the two reference places.
6. For questions comparing candidate pairs, parse both places in each option and compare the relevant metric for each pair.
7. Always return the exact candidate option text.
"""

COMMON_EVALUATION_RULES = """Common output rules:
- Return JSON only.
- JSON shape: {"predicted_answer": "exact option text", "predicted_option": 0, "confidence": 0.0, "reason": "brief English rationale"}.
- predicted_option is zero-based.
- predicted_answer must exactly equal one candidate option when possible.
- If evidence is incomplete, choose the best-supported option and set lower confidence.
- Never answer with text that is not one of the candidate options unless no option list is available.
"""

GENERAL_EVALUATION_PROMPT = BASE_EVALUATION_PROMPT + COMMON_EVALUATION_RULES


def get_evaluation_prompt(intent: str) -> str:
    """ intent  prompt"""
    intent_prompts = {
        "nearby": NEARBY_EVALUATION_PROMPT,
        "routing": ROUTING_EVALUATION_PROMPT,
        "trip": TRIP_EVALUATION_PROMPT,
        "poi": POI_EVALUATION_PROMPT,
    }

    intent_prompt = intent_prompts.get(intent, "")
    return BASE_EVALUATION_PROMPT + intent_prompt + COMMON_EVALUATION_RULES



def _configure_logging() -> logging.Logger:
    """"""
    logger = logging.getLogger("spatial_agent")
    if logger.handlers:
        return logger

    # , INFO
    log_level_str = os.getenv('SPATIAL_AGENT_LOG_LEVEL', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    # logs
    root_dir = Path(__file__).resolve().parents[2]
    log_dir = root_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # ()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    # :,
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


LOGGER = _configure_logging()


def _normalise_filename(text: str, max_length: int = 60) -> str:
    """"""
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_\-]", "", text)
    return text[:max_length] or "query"


def _attach_query_log(question: str, question_id: Optional[int] = None) -> logging.Handler:
    """"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    words = question.strip().split()[:5]
    slug = _normalise_filename(" ".join(words))

    if question_id is not None:
        filename = f"{timestamp}_id{question_id}_{slug}.log"
    else:
        filename = f"{timestamp}_{slug}.log"

    log_path = Path(__file__).resolve().parents[2] / "logs" / filename

    handler = logging.FileHandler(log_path, encoding="utf-8")
    # handlerlogger(DEBUG)
    handler.setLevel(LOGGER.level)
    # :,
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S"
    )
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)
    LOGGER.info("Attached per-query log handler: %s", log_path)
    return handler


class SpatialAgent:
    """
    Agent

    (Xu et al., 2023):
    - : AgentRouting()+ PlannerAgent(+DAG)
    - 
    - 
    """

    def __init__(
        self,
        google_api_key: str = None,
        openai_api_key: str = None
    ):
        """
        SpatialAgent

        Args:
            google_api_key: Google Maps API
            openai_api_key: OpenAI API
        """
        LOGGER.info("Initializing SpatialAgent with unified framework")

        # API
        self.google_client = GoogleMapsClient(google_api_key)
        self.llm = ChatOpenAI(
            api_key=openai_api_key or os.getenv('OPENAI_API_KEY'),
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            temperature=0
        )

        # (Phase 2)
        try:
            from src.tools.local_context_db import ContextManager
            db_path = Path(__file__).resolve().parents[2] / "data" / "context_cache.db"

            if db_path.exists():
                ContextManager.initialize_db(str(db_path))
                LOGGER.info(f"[GLOBAL_DB] : {db_path}")
            else:
                LOGGER.warning(f"[GLOBAL_DB] : {db_path}, Google Maps API")
        except Exception as e:
            LOGGER.warning(f"[GLOBAL_DB] : {e}, Google Maps API")

        # ()
        self.agent_routing = AgentRouting(self.llm)  # 
        self.planner_agent = PlannerAgent(self.llm)  #  + DAG
        self.transformation_executor = TransformationExecutor(self.google_client)
        self.answer_generator = AnswerGenerator(self.llm)    # 

        # 
        self.workflow = self._build_workflow()
        LOGGER.info("SpatialAgent initialized successfully")

    def _build_workflow(self) -> StateGraph:
        """
        

        :Route -> Plan -> Execute -> Evaluate -> Generate -> END
        """
        LOGGER.info("Building unified linear workflow")
        workflow = StateGraph(SpatialAgentState)

        # 
        workflow.add_node("route", self._route_with_cache_init)
        workflow.add_node("plan", self._plan_with_dag)
        workflow.add_node("execute", self._execute_with_preprocessing)
        workflow.add_node("evaluate", self._evaluate_with_llm)
        workflow.add_node("generate", self._generate_with_cache_cleanup)

        workflow.set_entry_point("route")
        workflow.add_edge("route", "plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", "evaluate")
        workflow.add_edge("evaluate", "generate")
        workflow.add_edge("generate", END)

        return workflow.compile()

    def _route_with_cache_init(self, state: SpatialAgentState) -> SpatialAgentState:
        """
         + Global Context DB 

        (Phase 2 ):
        1.  agent_routing.create_plan  intent 
        2.  intent  question_id( routing/trip)
        3.  intent ,

        Args:
            state:  question, options, question_id 

        Returns:
            , intent
        """
        # 1.  route 
        state = self.agent_routing.create_plan(state)

        # 2.  question_id(Phase 2: intent )
        question_id = state.get("question_id")

        # Note: question_id ()
        # intent  executors.py 

        return state

    def _generate_with_cache_cleanup(self, state: SpatialAgentState) -> SpatialAgentState:
        """
         + Global Context DB 

        (Phase 2 ):
        1.  answer_generator.generate_answer 
        2.  question_id()

        Args:
            state:  evaluation, transformation_plan 

        Returns:
            , final_answer
        """
        # 1.  generate 
        state = self.answer_generator.generate_answer(state)

        # 2.  question_id(Phase 2:)
        try:
            from src.tools.local_context_db import ContextManager
            ContextManager.clear()
            LOGGER.debug("[GLOBAL_DB] ")
        except Exception as e:
            LOGGER.debug(f"[GLOBAL_DB] : {e}")

        return state

    def _plan_with_dag(self, state: SpatialAgentState) -> SpatialAgentState:
        """
        : PlannerAgent DAG

        Args:
            state:  question, intent, options 

        Returns:
            , transformation_plan
        """
        # 
        LOGGER.info("=" * 80)
        LOGGER.info("[PLAN] Starting Plan Phase - Concept Extraction & DAG Generation")
        LOGGER.info("=" * 80)

        start_time = time.time()

        if state.get("error"):
            return state

        question = state["question"]
        intent = state.get("intent")
        options = state.get("options")

        if not intent:
            state["error"] = "Missing intent from routing stage"
            return state

        LOGGER.info(f"[_plan_with_dag]  PlannerAgent | intent={intent}")

        try:
            #  PlannerAgent  DAG
            transformation_plan = self.planner_agent.plan(
                question=question,
                intent=intent,
                options=options
            )

            # 
            state["transformation_plan"] = transformation_plan

            elapsed = time.time() - start_time
            debug_info = state.get("debug_info", {})
            debug_info["plan_duration"] = elapsed
            state["debug_info"] = debug_info

            LOGGER.info(f"[_plan_with_dag]  | types={len(transformation_plan.types)} | steps={len(transformation_plan.transformations)} | : {elapsed:.2f}s")

        except Exception as e:
            LOGGER.error(f"[_plan_with_dag] : {e}")
            state["error"] = f"Planning failed: {str(e)}"

        return state

    def _execute_with_preprocessing(self, state: SpatialAgentState) -> SpatialAgentState:
        """
        : TransformationExecutor  DAG
        """
        # 
        LOGGER.info("=" * 80)
        LOGGER.info("[EXECUTE] Starting Execute Phase - DAG Execution")
        LOGGER.info("=" * 80)

        start_time = time.time()

        if state.get("error"):
            return state

        LOGGER.info(": DAG ")

        #  TransformationExecutor 
        state = self.transformation_executor.execute(state)

        elapsed = time.time() - start_time
        debug_info = state.get("debug_info", {})
        debug_info["execute_duration"] = elapsed
        state["debug_info"] = debug_info
        LOGGER.info(f" | : {elapsed:.2f}s")

        return state

    def _evaluate_with_llm(self, state: SpatialAgentState) -> SpatialAgentState:
        """
         LLM 

         DAG , LLM 

         intent: nearby, routing, trip, poi
        """
        # 
        LOGGER.info("=" * 80)
        LOGGER.info("[EVALUATE] Starting Evaluate Phase - LLM-based Option Selection")
        LOGGER.info("=" * 80)

        start_time = time.time()

        if state.get("error"):
            return state

        question = state["question"]
        options = state.get("options", [])
        intent = state.get("intent", "unknown")

        if not options:
            LOGGER.info(f"[LLM Evaluation] , | intent={intent}")
            state["predicted_option"] = None
            state["evaluation"] = {"method": "no_options", "reason": ""}
            elapsed = time.time() - start_time
            debug_info = state.get("debug_info", {})
            debug_info["evaluate_duration"] = elapsed
            state["debug_info"] = debug_info
            return state

        LOGGER.info(f"[LLM Evaluation]  LLM  | intent={intent} | options={len(options)}")

        try:
            #  : intermediate_concepts 
            intermediate_concepts = state.get("intermediate_concepts", {})

            # :( Location )
            def serialize_value(value):
                """, Location """
                if hasattr(value, 'lat') and hasattr(value, 'lng'):  # Location 
                    return {
                        "name": getattr(value, 'name', None),
                        "lat": getattr(value, 'lat', None),
                        "lng": getattr(value, 'lng', None),
                        "address": getattr(value, 'address', None),
                        "rating": getattr(value, 'rating', None),
                        "opening_hours": getattr(value, 'opening_hours', None)
                    }
                elif isinstance(value, dict):
                    return {k: serialize_value(v) for k, v in value.items()}
                elif isinstance(value, list):
                    return [serialize_value(item) for item in value]
                else:
                    return value

            # 
            execution_results = {
                "origin_location": None,
                "locations": [],
                "api_results": {},
                "calculations": {},
                "concept_flow": state.get("concept_flow", []),
                "intermediate_concepts": {}
            }

            #  intermediate_concepts  origin_location
            if "geocoded_origin" in intermediate_concepts:
                origin_data = intermediate_concepts["geocoded_origin"]
                if isinstance(origin_data, dict) and 'origin_location' in origin_data:
                    origin = origin_data['origin_location']
                    if hasattr(origin, 'lat'):
                        execution_results["origin_location"] = serialize_value(origin)

            #  intermediate_concepts  locations( option_X  geocoded_origin)
            for concept_id, concept_data in intermediate_concepts.items():
                if isinstance(concept_data, dict) and 'locations' in concept_data:
                    for loc in concept_data['locations']:
                        execution_results["locations"].append(serialize_value(loc))
                elif concept_id.startswith('option_') and isinstance(concept_data, dict) and 'location' in concept_data:
                    execution_results["locations"].append(serialize_value(concept_data['location']))

            #  intermediate_concepts  API 
            if "candidates" in intermediate_concepts:
                execution_results["api_results"]["nearby_places"] = serialize_value(intermediate_concepts["candidates"])
            if "route" in intermediate_concepts:
                execution_results["api_results"]["directions"] = serialize_value(intermediate_concepts["route"])
            if "distance_matrix" in intermediate_concepts:
                execution_results["api_results"]["distance_matrix"] = serialize_value(intermediate_concepts["distance_matrix"])
            if "place_details" in intermediate_concepts:
                execution_results["api_results"]["place_details"] = serialize_value(intermediate_concepts["place_details"])

            #  :(route_0, route_1, route_2, ...)
            route_ids = sorted([k for k in intermediate_concepts.keys() if k.startswith('route_')])
            if route_ids:
                routes = {}
                for route_id in route_ids:
                    route_data = intermediate_concepts[route_id]
                    routes[route_id] = serialize_value(route_data)
                execution_results["api_results"]["routes"] = routes
                LOGGER.info(f"[LLM Evaluation]  {len(routes)} : {list(routes.keys())}")

            #  intermediate_concepts  calculations
            #  executors.py  state["calculations"], intermediate_concepts 
            if "geocoded_origin" in intermediate_concepts:
                origin_data = intermediate_concepts["geocoded_origin"]
                if isinstance(origin_data, dict) and 'origin_location' in origin_data:
                    origin = origin_data['origin_location']
                    if hasattr(origin, 'lat') and hasattr(origin, 'lng'):
                        option_distances = {}
                        option_ids = sorted([k for k in intermediate_concepts.keys() if k.startswith('option_')])
                        for option_id in option_ids:
                            option_data = intermediate_concepts[option_id]
                            if isinstance(option_data, dict):
                                option_loc = None
                                if 'locations' in option_data and option_data['locations']:
                                    option_loc = option_data['locations'][0]
                                elif 'location' in option_data:
                                    option_loc = option_data['location']

                                if option_loc and hasattr(option_loc, 'lat') and hasattr(option_loc, 'lng'):
                                    from .operators import haversine
                                    distance_m = haversine(origin.lat, origin.lng, option_loc.lat, option_loc.lng)
                                    option_distances[option_id] = {
                                        'name': option_loc.name,
                                        'distance_m': distance_m,
                                        'distance_km': distance_m / 1000
                                    }
                        if option_distances:
                            execution_results["calculations"]["option_distances"] = option_distances

            #  : intermediate_concepts()
            # :(route_0/1/2, geocoded_origin)
            excluded_concepts = {"geocoded_origin"}  #  origin_location 
            excluded_concepts.update(route_ids)  #  api_results["routes"] 

            for concept_id, concept_data in intermediate_concepts.items():
                if concept_id in excluded_concepts:
                    continue

                #  intermediate_concepts
                serialized_data = serialize_value(concept_data)
                execution_results["intermediate_concepts"][concept_id] = serialized_data

                # POI  calculations()
                if "_result" in concept_id or concept_id.startswith("distance_") or concept_id.startswith("direction_") or concept_id.startswith("bearing_"):
                    execution_results["calculations"][concept_id] = serialized_data

            #  : transformation_plan ( waypoints )
            transformation_plan = state.get("transformation_plan")
            if transformation_plan and hasattr(transformation_plan, 'transformations'):
                route_mappings = []
                for i, step in enumerate(transformation_plan.transformations):
                    if step.operator == "directions" and step.after:
                        #  ID  waypoints 
                        route_id = step.after[0] if step.after else None
                        waypoints = step.params.get("waypoints", [])
                        if route_id and waypoints:
                            route_mappings.append({
                                "route_id": route_id,
                                "waypoints": waypoints,
                                "step_index": i
                            })
                if route_mappings:
                    execution_results["route_mappings"] = route_mappings
                    LOGGER.info(f"[LLM Evaluation]  {len(route_mappings)} ")

            #  LLM 
            options_text = json.dumps(options, ensure_ascii=False, indent=2)
            results_text = json.dumps(execution_results, ensure_ascii=False, indent=2)

            user_input = f"""Question:
"{question}"

Candidate options:
{options_text}

Execution results:
{results_text}

Return the required JSON object only."""

            #   intent  prompt
            evaluation_prompt = get_evaluation_prompt(intent)

            #  LLM 
            LOGGER.info(f"[LLM Evaluation]  LLM  | intent={intent}")
            LOGGER.info("=" * 80)
            LOGGER.info(f"[LLM Evaluation] System Prompt (intent={intent}, len={len(evaluation_prompt)}):")
            LOGGER.info("-" * 80)
            LOGGER.info(evaluation_prompt)
            LOGGER.info("-" * 80)
            LOGGER.info("[LLM Evaluation] User Input:")
            LOGGER.info("-" * 80)
            LOGGER.info(user_input)
            LOGGER.info("=" * 80)

            #  LLM
            response = self.llm.invoke([
                SystemMessage(content=evaluation_prompt),
                HumanMessage(content=user_input)
            ])

            # 
            content = response.content.strip()
            LOGGER.info("-" * 80)
            LOGGER.info("[LLM Evaluation] LLM :")
            LOGGER.info("-" * 80)
            LOGGER.info(content)
            LOGGER.info("=" * 80)

            # Parse JSON and normalize legacy field names if the model follows the documented schema.
            result = self._extract_json_from_response(content)
            if result:
                if "predicted_answer" not in result and "answer" in result:
                    result["predicted_answer"] = result["answer"]
                if "predicted_option" not in result and "option_index" in result:
                    result["predicted_option"] = result["option_index"]

            # Handle predicted_answer first because it is safest to match exact option text.
            if result and "predicted_answer" in result:
                predicted_answer = str(result["predicted_answer"]).strip()
                reason = result.get("reason", "LLM ")

                # 
                state["predicted_answer"] = predicted_answer

                # ()
                matched_idx = None
                # :
                for idx, option in enumerate(options):
                    option_str = str(option).strip()
                    if predicted_answer.lower() == option_str.lower():
                        matched_idx = idx
                        break

                # :( "Via L1042"  "Via L1042 and Hainichlandweg" )
                if matched_idx is None:
                    best_match_idx = None
                    best_match_len = 0
                    for idx, option in enumerate(options):
                        option_str = str(option).strip()
                        if not option_str:  # 
                            continue
                        # ,
                        if predicted_answer.lower() in option_str.lower() or option_str.lower() in predicted_answer.lower():
                            # ,()
                            if len(option_str) > best_match_len:
                                best_match_idx = idx
                                best_match_len = len(option_str)
                    matched_idx = best_match_idx

                # :()
                #  predicted_answer (),
                if matched_idx is None and ',' in predicted_answer:
                    import re
                    # (,,)
                    def extract_address_keywords(addr):
                        # ,,
                        addr_clean = re.sub(r'[,./\-()]', ' ', addr.lower())
                        words = set(addr_clean.split())
                        # 
                        return {w for w in words if len(w) >= 2}

                    pred_keywords = extract_address_keywords(predicted_answer)
                    best_match_idx = None
                    best_match_score = 0

                    for idx, option in enumerate(options):
                        option_str = str(option).strip()
                        if not option_str or ',' not in option_str:
                            continue
                        option_keywords = extract_address_keywords(option_str)
                        # 
                        if pred_keywords and option_keywords:
                            overlap = len(pred_keywords & option_keywords)
                            #  Jaccard 
                            union = len(pred_keywords | option_keywords)
                            score = overlap / union if union > 0 else 0
                            if score > best_match_score and score >= 0.5:  #  50% 
                                best_match_score = score
                                best_match_idx = idx
                                LOGGER.info(f"[LLM Evaluation] : score={score:.2f}, option[{idx}]")

                    if best_match_idx is not None:
                        LOGGER.info(f"[LLM Evaluation] : '{predicted_answer}' -> [{best_match_idx}]")
                        matched_idx = best_match_idx

                if matched_idx is not None:
                    state["predicted_option"] = matched_idx
                    state["evaluation"] = {
                        "method": "llm_evaluation_text",
                        "intent": intent,
                        "reason": reason,
                        "predicted_answer": predicted_answer,
                        "predicted_option": matched_idx
                    }

                    elapsed = time.time() - start_time
                    debug_info = state.get("debug_info", {})
                    debug_info["evaluate_duration"] = elapsed
                    state["debug_info"] = debug_info

                    LOGGER.info(
                        f"[LLM Evaluation]  | intent={intent} | answer='{predicted_answer}' | "
                        f"reason={reason[:50]}... | : {elapsed:.2f}s"
                    )
                    return state
                else:
                    LOGGER.warning(f"[LLM Evaluation] : '{predicted_answer}' ")
                    # 

            #  (predicted_option )
            if result and "predicted_option" in result:
                predicted_option = result["predicted_option"]
                reason = result.get("reason", "LLM ")

                # 
                if isinstance(predicted_option, int) and 0 <= predicted_option < len(options):
                    # ,
                    state["predicted_option"] = predicted_option
                    state["predicted_answer"] = str(options[predicted_option]).strip()
                    state["evaluation"] = {
                        "method": "llm_evaluation",
                        "intent": intent,
                        "reason": reason,
                        "predicted_option": predicted_option,
                        "predicted_answer": state["predicted_answer"]
                    }

                    elapsed = time.time() - start_time
                    debug_info = state.get("debug_info", {})
                    debug_info["evaluate_duration"] = elapsed
                    state["debug_info"] = debug_info

                    LOGGER.info(
                        f"[LLM Evaluation]  | intent={intent} | predicted={predicted_option} | "
                        f"reason={reason[:50]}... | : {elapsed:.2f}s"
                    )
                    return state
                else:
                    #  :
                    LOGGER.warning(f"[LLM Evaluation] : {predicted_option} (: {len(options)})")
                    LOGGER.info("[LLM Evaluation] :")

                    #  predicted_option ,
                    predicted_str = str(predicted_option).strip()

                    for idx, option in enumerate(options):
                        option_str = str(option).strip()
                        # 
                        if predicted_str.lower() == option_str.lower():
                            LOGGER.info(f"[LLM Evaluation] : '{predicted_str}' -> [{idx}] = '{option_str}'")
                            state["predicted_option"] = idx
                            state["predicted_answer"] = option_str
                            state["evaluation"] = {
                                "method": "llm_evaluation_smart_match",
                                "intent": intent,
                                "reason": f": {reason}",
                                "predicted_option": idx,
                                "predicted_answer": option_str,
                                "original_value": predicted_option
                            }
                            elapsed = time.time() - start_time
                            debug_info = state.get("debug_info", {})
                            debug_info["evaluate_duration"] = elapsed
                            state["debug_info"] = debug_info
                            return state
                        # ()
                        if predicted_str.lower() in option_str.lower() or option_str.lower() in predicted_str.lower():
                            LOGGER.info(f"[LLM Evaluation] (): '{predicted_str}' ~ [{idx}] = '{option_str}'")
                            state["predicted_option"] = idx
                            state["predicted_answer"] = option_str
                            state["evaluation"] = {
                                "method": "llm_evaluation_smart_match",
                                "intent": intent,
                                "reason": f"(): {reason}",
                                "predicted_option": idx,
                                "predicted_answer": option_str,
                                "original_value": predicted_option
                            }
                            elapsed = time.time() - start_time
                            debug_info = state.get("debug_info", {})
                            debug_info["evaluate_duration"] = elapsed
                            state["debug_info"] = debug_info
                            return state

                    LOGGER.warning(f"[LLM Evaluation] :  '{predicted_str}' ")

            if result:
                LOGGER.warning("[LLM Evaluation] LLM  predicted_answer  predicted_option")
            else:
                LOGGER.warning("[LLM Evaluation]  LLM  JSON")

        except Exception as e:
            LOGGER.error(f"[LLM Evaluation] LLM : {e}", exc_info=True)

        # LLM,(0)
        LOGGER.warning("[LLM Evaluation] LLM ,(0)")
        state["predicted_option"] = 0
        state["predicted_answer"] = str(options[0]).strip() if options else ""
        state["evaluation"] = {
            "method": "llm_evaluation_failed",
            "intent": intent,
            "reason": "LLM ,",
            "predicted_option": 0,
            "predicted_answer": state["predicted_answer"]
        }
        elapsed = time.time() - start_time
        debug_info = state.get("debug_info", {})
        debug_info["evaluate_duration"] = elapsed
        state["debug_info"] = debug_info
        return state

    def _extract_json_from_response(self, content: str) -> Optional[Dict[str, Any]]:
        """ LLM  JSON"""
        # 
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        #  ```json ... ``` 
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        #  {...} 
        json_match = re.search(r'\{[^{}]*"predicted_option"[^{}]*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def process_question(
        self,
        question: str,
        options: Optional[List[str]] = None,
        correct_answer: Optional[int] = None,
        question_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        

        Args:
            question: 
            options: ()
            correct_answer: (,)
            question_id: ID(,)

        Returns:
            :
                - answer: 
                - intent: 
                - predicted_option: 
                - evaluation: 
                - locations: 
                - error: ()
        """
        query_handler: Optional[logging.Handler] = None

        try:
            # 
            initial_state = SpatialAgentState(
                question=question,
                options=options or [],
                correct_answer=correct_answer,
                question_id=question_id,  # : context cache
                parsed_info=None,
                intent=None,
                evaluation={},
                predicted_option=None,
                final_answer=None,
                error=None,
                debug_info={},
            )

            # 
            try:
                query_handler = _attach_query_log(question, question_id)
            except Exception as attach_error:
                LOGGER.warning("Failed to attach per-query log: %s", attach_error)

            # 
            log_separator(LOGGER)
            id_str = f"ID: {question_id}" if question_id else "Interactive"
            LOGGER.info(f"{SYMBOLS['lightning']} WORKFLOW STARTED | {id_str} | OPTIONS: {len(options or [])}")
            log_separator(LOGGER)
            LOGGER.info(f"Question: {question[:100]}{'...' if len(question) > 100 else ''}")
            LOGGER.info(f"Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
            LOGGER.info("")

            # 
            workflow_start_time = time.time()
            result = self.workflow.invoke(initial_state)
            workflow_duration = time.time() - workflow_start_time

            # 
            LOGGER.info("")
            summary_data = {
                "intent": result.get("intent"),
                "measure": result.get("transformation_plan").measure if result.get("transformation_plan") else None,
                "predicted_option": result.get("predicted_option"),
                "correct_answer": correct_answer
            }
            # TODO:  LLM  API 
            log_workflow_summary(LOGGER, workflow_duration, 2, 5, summary_data)

            # 
            debug_info = result.get("debug_info", {})
            if debug_info:
                LOGGER.info("")
                LOGGER.info(":")

                phase_names = []
                phase_durations = []

                # (:routegenerate,)
                if "plan_duration" in debug_info:
                    phase_names.append("Plan (+DAG)")
                    phase_durations.append([f"{debug_info['plan_duration']:.3f}s"])

                if "execute_duration" in debug_info:
                    phase_names.append("Execute ()")
                    phase_durations.append([f"{debug_info['execute_duration']:.3f}s"])

                if "evaluate_duration" in debug_info:
                    phase_names.append("Evaluate ()")
                    phase_durations.append([f"{debug_info['evaluate_duration']:.3f}s"])

                # 
                phase_names.append("Total ()")
                phase_durations.append([f"{workflow_duration:.3f}s"])

                if phase_names:
                    log_table(
                        LOGGER,
                        headers=["", ""],
                        rows=[[name] + duration for name, duration in zip(phase_names, phase_durations)],
                        alignments=['left', 'right']
                    )

            # ( intermediate_concepts )
            return {
                "answer": result.get("final_answer", ""),
                "intent": result.get("intent"),
                "intermediate_concepts": result.get("intermediate_concepts", {}),
                "concept_flow": result.get("concept_flow", []),
                "predicted_option": result.get("predicted_option"),
                "evaluation": result.get("evaluation", {}),
                "error": result.get("error"),
                "debug_info": result.get("debug_info", {}),
            }

        except Exception as e:
            LOGGER.exception("Failed to process question: %s", question)
            return {
                "answer": f":{str(e)}",
                "error": str(e),
                "intent": None,
                "predicted_option": None,
            }

        finally:
            # 
            if query_handler:
                LOGGER.removeHandler(query_handler)
                try:
                    query_handler.close()
                except Exception:
                    pass

    def get_workflow_graph(self) -> str:
        """
        Mermaid

        Returns:
            Mermaid
        """
        try:
            return self.workflow.get_graph().draw_mermaid()
        except Exception as e:
            LOGGER.error(f"Failed to generate workflow graph: {e}")
            return ""


def create_spatial_agent(
    google_api_key: str = None,
    openai_api_key: str = None
) -> SpatialAgent:
    """
    SpatialAgent

    Args:
        google_api_key: Google Maps API
        openai_api_key: OpenAI API

    Returns:
        SpatialAgent
    """
    return SpatialAgent(
        google_api_key=google_api_key,
        openai_api_key=openai_api_key
    )
