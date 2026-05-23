"""
PlannerAgent - 

 ( Xu et al., 2023):
1.  Core Concepts + Functional Roles ( LLM + intent-specific prompt)
2. : Extent -> Temporal -> Sub-condition -> Condition -> Support -> Measure
3. (object -> field, field -> field -> object)
4. 
5.  before/after  DAG

:
- : plan() -> _extract_concepts_and_dag_with_llm()
-  intent-specific prompts (NEARBY/POI/ROUTING/TRIP_COMPLETE_PROMPT)
-  + DAG
- 4  intent x 4-8  Few-Shot 
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .state import (
    CoreConcept, FunctionalRole, ConceptEntity,
    TransformationPlan, TransformationStep
)

logger = logging.getLogger("spatial_agent.planner")


#  ()
ROLE_PRIORITY_ORDER = {
    FunctionalRole.EXTENT: 0,
    FunctionalRole.TEMPORAL_EXTENT: 1,
    FunctionalRole.SUB_CONDITION: 2,
    FunctionalRole.CONDITION: 3,
    FunctionalRole.SUPPORT: 4,
    FunctionalRole.MEASURE: 5,
}




# ============================================================================
# LLM-Driven DAG Construction Prompts
# ============================================================================

COMMON_PLANNING_RULES = """You are a spatial-query planning expert. Given one MapEval-style question and its candidate options, return an executable JSON plan.

Hard requirements:
1. Prefer local database operators whenever possible. Use Google Maps API operators only as fallback.
2. Use only operators that exist in the registry. Never invent operators.
3. Use actual place names in params when an operator expects place names.
4. Return JSON only. Do not include markdown, comments, or prose.
5. Keep candidate option text available for the evaluator; do not answer the question in the plan.

Concept types:
- location: a discrete place or position.
- object: a point of interest or candidate place.
- field: route, coordinate, bearing, distance, duration, opening status, or similar spatial field.
- amount: a numeric value, rank, count, duration, distance, or time budget.

Functional roles:
- extent: user location, origin, spatial scope, or anchor place.
- temporal_extent: day, time, start time, deadline, or time budget.
- sub_condition: rating, price, category, opening-hours, route name, travel mode, radius, or via constraint.
- condition: candidate place, destination, waypoint, or target entity.
- support: intermediate result needed for another operator.
- measure: requested answer target such as nearest, count, direction, duration, route, order, schedule, or feasibility.

Available local database operators, preferred first:
- query_local_place(place_name)
- query_local_coordinates(place_name)
- query_local_routes(origin, destination, mode)
- query_local_travel_time(origin, destination, mode)
- query_local_places_batch(place_names, fallback_to_api=True)
- query_local_nearby_places(reference_place, category=None, radius_meters=None)

Available Google Maps fallback operators:
- geocode, batch_geocode, reverse_geocode
- place_search, place_details, batch_place_details
- directions, distance_matrix, timezone

Available computation operators:
- haversine, bearing, bearing_to_direction
- open_at_time, is_open_at_time_text, filter_places_by_time, filter_places
- nearest, within_radius, steps_analysis, pairwise_extremes
- compare_routes, filter_routes, extract_distance, extract_duration, count_in_route
- calculate_finish_time, calculate_arrival_time, calculate_latest_visit_time, calculate_latest_departure
- feasibility_check, add_durations, tsp_tw, service_area

Required JSON shape:
{
  "concept_entities": [
    {
      "name": "source text or inferred concept",
      "concept_type": "location|object|field|amount",
      "functional_role": "extent|temporal_extent|sub_condition|condition|support|measure",
      "attributes": {}
    }
  ],
  "transformations": [
    {
      "before": ["actual input names or previous output ids"],
      "after": ["stable_output_id"],
      "operator": "operator_name",
      "description": "short English description",
      "params": {}
    }
  ],
  "measure": "nearest|count|attribute|comparison|direction|route|duration|distance|order|schedule|departure_time|feasibility|total_time",
  "mode": "driving|walking|transit|bicycling",
  "params": {}
}

Validation checklist:
- The top-level key must be concept_entities, not concepts.
- Every operator must be listed above.
- For local operators, put the actual place names in params: place_name, place_names, reference_place, origin, destination, mode.
- For radius questions, preserve radius_meters as a number.
- For opening-hours questions, preserve day_of_week and target_time.
- For option-based questions, plan evidence collection; the evaluator will choose the exact option.
"""

NEARBY_COMPLETE_PROMPT = COMMON_PLANNING_RULES + """
Nearby intent rules:
- Use nearby when the question asks for places near an anchor, nearest/closest Nth item, places within a radius, nearby recommendations, or counts of nearby places.
- First call query_local_nearby_places with reference_place and category when the question has an anchor place and place type.
- For nearest, second nearest, highest rating, lowest rating, most reviews, or fewest reviews, preserve the full ranked nearby list for the evaluator.
- For open-at-time nearby questions, call query_local_nearby_places first and then filter_places_by_time.
- For radius questions such as within 500 meters, pass radius_meters to query_local_nearby_places.
- Do not geocode every option unless local nearby data is unavailable.

Example: hungry near Khansa Market
{
  "concept_entities": [
    {"name": "Khansa Market", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "restaurant candidates", "concept_type": "object", "functional_role": "condition", "attributes": {"category": "restaurant"}},
    {"name": "nearest suitable restaurant", "concept_type": "object", "functional_role": "measure", "attributes": {"measure_type": "nearest"}}
  ],
  "transformations": [
    {"before": ["Khansa Market"], "after": ["nearby_restaurants"], "operator": "query_local_nearby_places", "description": "Fetch locally cached restaurants near Khansa Market", "params": {"reference_place": "Khansa Market", "category": "restaurant"}}
  ],
  "measure": "nearest",
  "mode": "driving",
  "params": {}
}

Example: count cafes within 500 meters
{
  "concept_entities": [
    {"name": "Tokyo Tower", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "cafes within 500 meters", "concept_type": "object", "functional_role": "condition", "attributes": {"category": "cafe", "radius_meters": 500}},
    {"name": "number of matching cafes", "concept_type": "amount", "functional_role": "measure", "attributes": {"measure_type": "count"}}
  ],
  "transformations": [
    {"before": ["Tokyo Tower"], "after": ["nearby_cafes"], "operator": "query_local_nearby_places", "description": "Fetch cached cafes within 500 meters of Tokyo Tower", "params": {"reference_place": "Tokyo Tower", "category": "cafe", "radius_meters": 500}}
  ],
  "measure": "count",
  "mode": "walking",
  "params": {"radius_meters": 500}
}

Example: nearby places open at a specific time
{
  "concept_entities": [
    {"name": "Dubai Mall", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "restaurants", "concept_type": "object", "functional_role": "condition", "attributes": {"category": "restaurant"}},
    {"name": "Tuesday 9:15 AM", "concept_type": "field", "functional_role": "temporal_extent", "attributes": {"day_of_week": "Tuesday", "target_time": "9:15 AM"}},
    {"name": "open nearby restaurant", "concept_type": "object", "functional_role": "measure", "attributes": {"measure_type": "nearest_open"}}
  ],
  "transformations": [
    {"before": ["Dubai Mall"], "after": ["nearby_restaurants"], "operator": "query_local_nearby_places", "description": "Fetch locally cached nearby restaurants", "params": {"reference_place": "Dubai Mall", "category": "restaurant"}},
    {"before": ["nearby_restaurants"], "after": ["open_restaurants"], "operator": "filter_places_by_time", "description": "Keep restaurants open at the requested time", "params": {"day_of_week": "Tuesday", "target_time": "9:15 AM"}}
  ],
  "measure": "nearest",
  "mode": "walking",
  "params": {"day_of_week": "Tuesday", "target_time": "9:15 AM"}
}
"""

POI_COMPLETE_PROMPT = COMMON_PLANNING_RULES + """
POI intent rules:
- Use POI for attributes of known places, opening hours, ratings, addresses, direction/bearing between two places, pairwise place comparisons, and between/closest-to-each-other questions without a user-location nearby anchor.
- Prefer query_local_place or query_local_places_batch for place attributes and coordinates.
- For direction questions, fetch coordinates for both places, then use bearing and bearing_to_direction.
- For distance comparisons among option places, fetch all option places with query_local_places_batch and let the evaluator compare coordinates or returned attributes.
- For opening-hours yes/no or option questions, use query_local_place first; use open_at_time when a specific day/time is requested.

Example: direction from one place to another
{
  "concept_entities": [
    {"name": "Cork City", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "Blarney Castle", "concept_type": "location", "functional_role": "condition", "attributes": {}},
    {"name": "direction from Cork City to Blarney Castle", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "direction"}}
  ],
  "transformations": [
    {"before": ["Cork City"], "after": ["cork_coordinates"], "operator": "query_local_coordinates", "description": "Fetch Cork City coordinates from local cache", "params": {"place_name": "Cork City"}},
    {"before": ["Blarney Castle"], "after": ["blarney_coordinates"], "operator": "query_local_coordinates", "description": "Fetch Blarney Castle coordinates from local cache", "params": {"place_name": "Blarney Castle"}},
    {"before": ["cork_coordinates", "blarney_coordinates"], "after": ["bearing_result"], "operator": "bearing", "description": "Compute bearing from Cork City to Blarney Castle", "params": {"origin": "cork_coordinates", "destination": "blarney_coordinates"}},
    {"before": ["bearing_result"], "after": ["direction_result"], "operator": "bearing_to_direction", "description": "Convert bearing into a cardinal or intercardinal direction", "params": {"bearing": "bearing_result"}}
  ],
  "measure": "direction",
  "mode": "driving",
  "params": {}
}

Example: opening time for a known place
{
  "concept_entities": [
    {"name": "Asador Etxebarri", "concept_type": "object", "functional_role": "condition", "attributes": {}},
    {"name": "Saturday 5:00 PM", "concept_type": "field", "functional_role": "temporal_extent", "attributes": {"day": "Saturday", "time": "5:00 PM"}},
    {"name": "open status", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "opening_hours"}}
  ],
  "transformations": [
    {"before": ["Asador Etxebarri"], "after": ["place_details"], "operator": "query_local_place", "description": "Fetch local place details including opening hours", "params": {"place_name": "Asador Etxebarri"}},
    {"before": ["place_details"], "after": ["open_status"], "operator": "open_at_time", "description": "Check whether the place is open at the requested time", "params": {"day": "Saturday", "time": "5:00 PM"}}
  ],
  "measure": "attribute",
  "mode": "driving",
  "params": {"day": "Saturday", "time": "5:00 PM"}
}

Example: compare places in candidate options
{
  "concept_entities": [
    {"name": "candidate places", "concept_type": "object", "functional_role": "condition", "attributes": {}},
    {"name": "pairwise spatial comparison", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "comparison"}}
  ],
  "transformations": [
    {"before": ["candidate places"], "after": ["candidate_place_details"], "operator": "query_local_places_batch", "description": "Fetch local details and coordinates for all candidate options", "params": {"place_names": []}}
  ],
  "measure": "comparison",
  "mode": "driving",
  "params": {}
}
"""

ROUTING_COMPLETE_PROMPT = COMMON_PLANNING_RULES + """
Routing intent rules:
- Use routing for origin-destination route questions, route summaries, next-step questions after reaching a road, distance/duration of routes, via-route constraints, and route choice.
- Prefer query_local_routes. The local route summary often contains all alternatives and step text, so do not add steps_analysis unless the plan needs a structured next-step extraction.
- If the question gives only a destination, query_local_routes can use destination without origin; the local cache may resolve a matching route.
- Preserve route names such as "Via Parsons Ave and E Main St" in params.route_name or params.via_route.
- Preserve reference roads or landmarks mentioned after "after reaching" in params.after.
- Use extract_duration, extract_distance, count_in_route, compare_routes, or filter_routes only when the route object needs a direct computed value.

Example: next step on a named route
{
  "concept_entities": [
    {"name": "Brassica", "concept_type": "location", "functional_role": "condition", "attributes": {}},
    {"name": "Grandview Avenue", "concept_type": "field", "functional_role": "sub_condition", "attributes": {"after": "Grandview Avenue"}},
    {"name": "next navigation instruction", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "next_step"}}
  ],
  "transformations": [
    {"before": ["Brassica"], "after": ["local_routes"], "operator": "query_local_routes", "description": "Fetch locally cached route alternatives to Brassica", "params": {"destination": "Brassica", "mode": "driving", "after": "Grandview Avenue"}}
  ],
  "measure": "route",
  "mode": "driving",
  "params": {"after": "Grandview Avenue"}
}

Example: route from A to B via a named route
{
  "concept_entities": [
    {"name": "origin place", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "destination place", "concept_type": "location", "functional_role": "condition", "attributes": {}},
    {"name": "named via route", "concept_type": "field", "functional_role": "sub_condition", "attributes": {"via_route": "specified route name"}},
    {"name": "route choice", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "route"}}
  ],
  "transformations": [
    {"before": ["origin place", "destination place"], "after": ["local_routes"], "operator": "query_local_routes", "description": "Fetch local route alternatives between origin and destination", "params": {"origin": "origin place", "destination": "destination place", "mode": "driving", "via_route": "specified route name"}}
  ],
  "measure": "route",
  "mode": "driving",
  "params": {"via_route": "specified route name"}
}
"""

TRIP_COMPLETE_PROMPT = COMMON_PLANNING_RULES + """
Trip intent rules:
- Use trip when the question has three or more places, an itinerary, a schedule, multiple sequential visits, visit durations, time budgets, finish-by constraints, or best-order questions.
- Prefer query_local_travel_time for every travel segment that is explicitly or implicitly needed.
- For fixed-order total-time questions, create one query_local_travel_time step per segment, then add_durations if a total duration is needed.
- For ordering questions with candidate option sequences, collect the travel-time evidence needed for the evaluator to compare each sequence.
- For feasibility and schedules, preserve start time, deadline, visit durations, and time budget in concept attributes and top-level params.
- Use tsp_tw only when the question asks for an optimized order and enough location/time-window information is available.

Example: fixed sequential trip total time
{
  "concept_entities": [
    {"name": "hotel", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "first attraction", "concept_type": "location", "functional_role": "condition", "attributes": {}},
    {"name": "second attraction", "concept_type": "location", "functional_role": "condition", "attributes": {}},
    {"name": "total travel time", "concept_type": "amount", "functional_role": "measure", "attributes": {"measure_type": "total_time"}}
  ],
  "transformations": [
    {"before": ["hotel", "first attraction"], "after": ["travel_hotel_to_first"], "operator": "query_local_travel_time", "description": "Fetch local travel time for the first segment", "params": {"origin": "hotel", "destination": "first attraction", "mode": "driving"}},
    {"before": ["first attraction", "second attraction"], "after": ["travel_first_to_second"], "operator": "query_local_travel_time", "description": "Fetch local travel time for the second segment", "params": {"origin": "first attraction", "destination": "second attraction", "mode": "driving"}},
    {"before": ["travel_hotel_to_first", "travel_first_to_second"], "after": ["total_travel_time"], "operator": "add_durations", "description": "Sum the segment travel times", "params": {}}
  ],
  "measure": "total_time",
  "mode": "driving",
  "params": {}
}

Example: optimized visit order
{
  "concept_entities": [
    {"name": "start place", "concept_type": "location", "functional_role": "extent", "attributes": {}},
    {"name": "places to visit", "concept_type": "object", "functional_role": "condition", "attributes": {"places": []}},
    {"name": "best visiting order", "concept_type": "field", "functional_role": "measure", "attributes": {"measure_type": "order"}}
  ],
  "transformations": [
    {"before": ["places to visit"], "after": ["visit_place_details"], "operator": "query_local_places_batch", "description": "Fetch local details and coordinates for places to visit", "params": {"place_names": []}},
    {"before": ["start place", "visit_place_details"], "after": ["optimized_trip"], "operator": "tsp_tw", "description": "Compute an optimized visit order when enough data is available", "params": {"locations": [], "mode": "driving"}}
  ],
  "measure": "order",
  "mode": "driving",
  "params": {}
}
"""


class PlannerAgent:
    """
    

    : ->  -> DAG 
    """

    def __init__(self, llm: ChatOpenAI):
        self.logger = logging.getLogger("spatial_agent.planner")
        self.llm = llm

    def plan(
        self,
        question: str,
        options: Optional[List[str]] = None,
        retrieved_examples: Optional[List[Dict]] = None,
        intent: Optional[str] = None  # 
    ) -> TransformationPlan:
        """
        ( RAP)

        Args:
            question: 
            options: 
            retrieved_examples: (RAP )
            intent: (,)

        Returns:
            TransformationPlan:  types + transformations
        """
        # RAP :
        if retrieved_examples is not None:
            self.logger.info(f"[PlannerAgent]  RAP  | examples={len(retrieved_examples)}")
            return self._plan_with_retrieval(question, options, retrieved_examples)

        # : intent  prompt()
        if intent is None:
            raise ValueError(" retrieved_examples  intent")

        self.logger.info(f"[PlannerAgent]  | intent={intent} | options={len(options) if options else 0}")

        # ()
        concept_entities = self._extract_concepts_and_dag_with_llm(question, intent, options)
        self.logger.info(f"[PlannerAgent]  {len(concept_entities)} ")

        grouped = self._group_by_role(concept_entities)
        execution_order = self._determine_order(grouped)
        self.logger.info(f"[PlannerAgent] : {[role.value for role, _ in execution_order]}")

        expanded_types, transformations = self._build_dag(
            intent=intent,
            concept_entities=concept_entities
        )
        self.logger.info(f"[PlannerAgent]  {len(transformations)} ")

        extent, temporal, mode, params = self._extract_global_params(expanded_types)
        measure_type = self._determine_measure_type(grouped, intent)

        plan = TransformationPlan(
            types=expanded_types,
            extent=extent,
            temporal=temporal,
            transformations=transformations,
            measure=measure_type,
            mode=mode,
            params=params
        )

        self.logger.info(f"[PlannerAgent]  | types={len(expanded_types)} | steps={len(transformations)}")
        return plan

    def _extract_concepts_and_dag_with_llm(
        self,
        question: str,
        intent: str,
        options: Optional[List[str]]
    ) -> List[ConceptEntity]:
        """
         LLM  DAG( intent)

         transformations  self._llm_transformations
        """
        #  intent-specific prompt
        if intent == "nearby":
            prompt = NEARBY_COMPLETE_PROMPT
        elif intent == "poi":
            prompt = POI_COMPLETE_PROMPT
        elif intent == "routing":
            prompt = ROUTING_COMPLETE_PROMPT
        elif intent == "trip":
            prompt = TRIP_COMPLETE_PROMPT
        else:
            #  intent, nearby prompt
            prompt = NEARBY_COMPLETE_PROMPT

        options_text = json.dumps(options, ensure_ascii=False, indent=2) if options else "[]"

        user_input = f"""Question:
"{question}"

Candidate options:
{options_text}

Return the required JSON object only."""

        try:
            import time
            from ..utils.logging_utils import log_llm_call

            start_time = time.time()
            response = self.llm.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=user_input)
            ])
            duration = time.time() - start_time

            #  token 
            tokens = None
            if hasattr(response, 'response_metadata'):
                token_usage = response.response_metadata.get('token_usage', {})
                if token_usage:
                    tokens = {
                        'input': token_usage.get('prompt_tokens', 0),
                        'output': token_usage.get('completion_tokens', 0),
                        'total': token_usage.get('total_tokens', 0)
                    }

            #  LLM 
            log_llm_call(
                logger=self.logger,
                stage=f"Plan-Concepts-{intent.upper()}",
                system_prompt=prompt,
                user_input=user_input,
                response=response.content,
                duration=duration,
                tokens=tokens
            )

            result = self._extract_json(response.content.strip())

            # Parse concept entities. The release prompt briefly used "concepts";
            # keep a compatibility path but normalize internally to concept_entities.
            raw_entities = result.get("concept_entities")
            if raw_entities is None:
                raw_entities = result.get("concepts", [])

            concept_entities = []
            for entity_dict in raw_entities:
                try:
                    concept_type_str = entity_dict.get("type") or entity_dict.get("concept_type", "")
                    role_str = entity_dict.get("role") or entity_dict.get("functional_role", "")
                    name = entity_dict.get("name") or entity_dict.get("text") or entity_dict.get("id", "")
                    attributes = dict(entity_dict.get("attributes", {}) or {})
                    if entity_dict.get("id") and "id" not in attributes:
                        attributes["id"] = entity_dict["id"]

                    concept_type = self._parse_concept_type(concept_type_str)
                    functional_role = self._parse_functional_role(role_str)

                    concept_entities.append(ConceptEntity(
                        name=name,
                        concept_type=concept_type,
                        functional_role=functional_role,
                        attributes=attributes
                    ))
                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Invalid concept entity: {entity_dict}, error: {e}")

            #   transformations ()
            transformations = []
            for i, step_dict in enumerate(result.get("transformations", [])):
                try:
                    operator_name = step_dict.get("operator", "")

                    # P0: 
                    from src.agent.operators import validate_operator
                    if not validate_operator(operator_name):
                        self.logger.error(
                            f"[Hierarchical Planning] ERROR  {i+1} : '{operator_name}'\n"
                            f"  : {step_dict.get('description', 'N/A')}"
                        )
                        continue

                    transformations.append(TransformationStep(
                        before=step_dict.get("before", []),
                        after=step_dict.get("after", []),
                        operator=operator_name,
                        description=step_dict.get("description"),
                        params=step_dict.get("params", {})
                    ))
                except Exception as e:
                    self.logger.warning(f"Invalid transformation: {step_dict}, error: {e}")

            # ( _build_dag )
            self._llm_transformations = transformations
            self.logger.info(f"[Plan-Concepts-{intent.upper()}]  {len(concept_entities)} ,{len(transformations)} ")

            # 
            if concept_entities:
                self.logger.info(f"[Plan-Concepts-{intent.upper()}] :")
                for i, entity in enumerate(concept_entities, 1):
                    self.logger.info(f"  {i}. {entity.name} | type={entity.concept_type.value} | role={entity.functional_role.value}")

            return concept_entities

        except Exception as e:
            self.logger.error(f"[LLM Planning]  DAG : {e} | intent={intent}")
            return []

    def _extract_json(self, text: str) -> Dict:
        """ LLM  JSON"""
        import re

        #  JSON 
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        else:
            #  {  }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end+1]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def _parse_concept_type(self, type_str: str) -> CoreConcept:
        """ CoreConcept 

        :
        1. : "location", "object", "field" 
        2. : CoreConcept.LOCATION 

        Args:
            type_str: 

        Returns:
            CoreConcept , OBJECT
        """
        if isinstance(type_str, CoreConcept):
            return type_str

        # ()
        type_mapping = {
            'location': CoreConcept.LOCATION,
            'object': CoreConcept.OBJECT,
            'field': CoreConcept.FIELD,
            'event': CoreConcept.EVENT,
            'network': CoreConcept.NETWORK,
            'amount': CoreConcept.AMOUNT,
            'proportion': CoreConcept.PROPORTION,
        }

        type_lower = str(type_str).lower().strip()
        return type_mapping.get(type_lower, CoreConcept.OBJECT)

    def _parse_functional_role(self, role_str: str) -> FunctionalRole:
        """ FunctionalRole 

        :
        1. : "extent", "condition", "measure" 
        2. : FunctionalRole.EXTENT 

        Args:
            role_str: 

        Returns:
            FunctionalRole , SUPPORT
        """
        if isinstance(role_str, FunctionalRole):
            return role_str

        # ()
        role_mapping = {
            'extent': FunctionalRole.EXTENT,
            'temporal_extent': FunctionalRole.TEMPORAL_EXTENT,
            'sub_condition': FunctionalRole.SUB_CONDITION,
            'condition': FunctionalRole.CONDITION,
            'support': FunctionalRole.SUPPORT,
            'measure': FunctionalRole.MEASURE,
        }

        role_lower = str(role_str).lower().strip()
        return role_mapping.get(role_lower, FunctionalRole.SUPPORT)

    def _group_by_role(
        self,
        entities: List[ConceptEntity]
    ) -> Dict[FunctionalRole, List[ConceptEntity]]:
        """"""
        grouped = {}
        for entity in entities:
            role = entity.functional_role
            if role:
                if role not in grouped:
                    grouped[role] = []
                grouped[role].append(entity)
        return grouped

    def _determine_order(
        self,
        grouped: Dict[FunctionalRole, List[ConceptEntity]]
    ) -> List[Tuple[FunctionalRole, List[ConceptEntity]]]:
        """
        

        : Extent -> Temporal -> Sub-condition -> Condition -> Support -> Measure
        """
        sorted_roles = sorted(
            grouped.items(),
            key=lambda x: ROLE_PRIORITY_ORDER.get(x[0], 99)
        )
        return sorted_roles

    def _build_dag(
        self,
        intent: str,
        concept_entities: List[ConceptEntity]
    ) -> Tuple[List[ConceptEntity], List[TransformationStep]]:
        """
         DAG( LLM )

         LLM ,

        Args:
            intent: 
            concept_entities: 

        Returns:
            (expanded_types, transformations) - 

        Note:
             _extract_concepts_and_dag_with_llm() 
            _llm_transformations  LLM 
        """
        #   LLM  DAG
        if hasattr(self, '_llm_transformations'):
            transformations = self._llm_transformations
            delattr(self, '_llm_transformations')  # 
            self.logger.info(f"[LLM Planning]  LLM  DAG, {len(transformations)}  | intent={intent}")
            return concept_entities, transformations
        else:
            #  LLM ,
            self.logger.warning(f"[LLM Planning]  LLM  DAG, | intent={intent}")
            return concept_entities, []

    # ========================================================================
    # ( measure )
    # ========================================================================

    def _extract_global_params(
        self,
        concept_entities: List[ConceptEntity]
    ) -> Tuple[List[str], List[str], str, Dict[str, Any]]:
        """
        

        Returns:
            extent, temporal, mode, params
        """
        extent = []
        temporal = []
        mode = "driving"
        params = {}

        # 
        for entity in concept_entities:
            if entity.functional_role == FunctionalRole.EXTENT:
                extent.append(entity.name)
            elif entity.functional_role == FunctionalRole.TEMPORAL_EXTENT:
                temporal.append(entity.name)

            # 
            if "mode" in entity.attributes:
                mode = entity.attributes["mode"]
            if "transportation_mode" in entity.attributes:
                mode = entity.attributes["transportation_mode"]

            #  params
            for key, value in entity.attributes.items():
                if key not in ["mode", "transportation_mode"]:
                    params[key] = value

        return extent, temporal, mode, params

    def _determine_measure_type(
        self,
        grouped: Dict[FunctionalRole, List[ConceptEntity]],
        intent: str
    ) -> str:
        """
         measure 

         measure 
        """
        #  intent
        intent_to_measure = {
            "nearby": "nearest",
            "routing": "route",
            "trip": "order",
            "poi": "attribute"
        }

        default_measure = intent_to_measure.get(intent, "unknown")

        #  measure 
        measure_entities = grouped.get(FunctionalRole.MEASURE, [])
        if measure_entities:
            measure_entity = measure_entities[0]
            # 
            if measure_entity.concept_type == CoreConcept.AMOUNT:
                if "distance" in measure_entity.name.lower():
                    return "distance"
                elif "count" in measure_entity.name.lower():
                    return "count"
                elif "bearing" in measure_entity.name.lower() or "direction" in measure_entity.name.lower():
                    return "bearing"

        return default_measure
