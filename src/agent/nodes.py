import html
import json
import logging
import math
import re
from datetime import datetime, time as dt_time
from dataclasses import asdict
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .state import (
    Location, ParsedInfo, SpatialAgentState,
    CoreConcept, FunctionalRole, ConceptEntity,
    TransformationPlan, TransformationStep
)
from ..utils.logging_utils import normalize_text


LOGGER = logging.getLogger("spatial_agent.nodes")


# ==================== Global Constants ====================

PRIMARY_DIRECTIONS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
]


# ====================  ====================

def extract_json_from_llm_response(raw: str) -> Optional[Dict[str, Any]]:
    """
     LLM  JSON

    :
    1.  JSON: '{"intent": "nearby"}'
    2.  JSON: ': {"intent": "nearby"}'

    Args:
        raw: LLM 

    Returns:
        , None

    Examples:
        >>> extract_json_from_llm_response('{"intent": "nearby"}')
        {'intent': 'nearby'}

        >>> extract_json_from_llm_response(': {"intent": "trip"}')
        {'intent': 'trip'}

        >>> extract_json_from_llm_response('invalid text')
        None
    """
    if not raw:
        return None

    #  1:  JSON 
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    #  2:  {...} 
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


# ====================  ====================

class AgentRouting:
    """"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.logger = logging.getLogger("spatial_agent.nodes.AgentRouting")

    def create_plan(self, state: SpatialAgentState) -> SpatialAgentState:
        """
        

        :,
        """
        # 
        self.logger.info("=" * 80)
        self.logger.info("[ROUTE] Starting Route Phase - Intent Classification")
        self.logger.info("=" * 80)

        if state.get("error"):
            return state

        question = state["question"]
        options = state.get("options") or []

        self.logger.info(
            "AgentRouting received question. options=%d",
            len(options)
        )

        #  intent
        intent = self._classify_intent(question, options)
        self.logger.info(f"Intent classified: {intent}")

        state["intent"] = intent

        return state

    def _classify_intent(self, question: str, options: List[str]) -> str:
        """
         LLM 
        """
        system_prompt = """You are an intent classifier for a spatial reasoning agent. Classify the question into exactly one intent and return JSON only: {"intent": "nearby|routing|trip|poi"}.

Intent definitions:

nearby:
- The user has an anchor/current location and asks for nearby places, recommendations, nearest/closest items, Nth nearest items, places within a radius, or counts of places around an anchor.
- Typical patterns: "I am at X, suggest a nearby restaurant", "nearest park to Y", "second nearest library to Y", "how many cafes within 500m of Y", "which restaurant near Y has highest rating".
- Do not use nearby for pairwise comparisons among candidate places without an anchor; those are poi.
- Do not use nearby for multi-stop visits; those are trip.

routing:
- The question asks for a route, navigation instruction, route distance/duration, how to get from A to B, route alternatives, via-route constraints, or the next instruction after reaching a road or landmark.
- Use routing even when there are waypoints or a named "Via ..." route, as long as the question is about navigation between origin and destination rather than a multi-stop itinerary.
- Examples: "How do I get from A to B?", "What is the distance from A to B?", "I am driving from A to B via C. After reaching D, where should I go next?".

trip:
- The question is about an itinerary, schedule, multiple visits, best/optimal order, feasibility within a time budget, arrival/departure times, or total trip time across several legs.
- Strong signals: three or more places, "visit A, then B, then C", "best order", "schedule", "itinerary", "can I visit all", "finish by", "latest departure", explicit visit durations.
- If the question says "go from A to B, then visit C" or asks about visiting multiple places, classify as trip rather than routing.

poi:
- The question asks about attributes or spatial relationships of known places, not a nearby search or route: opening hours, rating, address, price, direction/bearing from one place to another, which pair is closest/farthest, which place is between two places, or whether a single POI is open at a time.
- Examples: "What time does X open?", "What is the rating of Y?", "What direction is X from Y?", "Which pair of places is closest to each other?", "Which coffee shop is between A and B?", "Can I visit X at 5 PM Saturday?".

Priority rules:
1. Multi-stop itinerary or time-budget visit planning -> trip.
2. Anchor plus nearby/nearest/within-radius/count around anchor -> nearby.
3. Origin-destination navigation, route alternatives, via-route, next instruction -> routing.
4. Place attributes, pairwise comparison, between, bearing/direction -> poi.

Return exactly one JSON object and no explanatory text."""

        try:
            import time
            from ..utils.logging_utils import log_llm_call

            options_text = json.dumps(options, ensure_ascii=False)
            user_input = f"Question: {question}\nOptions: {options_text}\nReturn JSON only."

            start_time = time.time()
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
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
                stage="Route",
                system_prompt=system_prompt,
                user_input=user_input,
                response=response.content,
                duration=duration,
                tokens=tokens
            )

            result = extract_json_from_llm_response(response.content.strip())
            if result and "intent" in result:
                self.logger.info(f"[Route] Extracted intent: {result['intent']}")
                return result["intent"]
        except Exception as e:
            self.logger.warning(f"LLM intent classification failed: {e}")

        # 
        return self._infer_intent(question)

    def _infer_intent(self, question: str) -> str:
        """
        : LLM 

        ( System Prompt ):
        1.  + nearby  -> NEARBY
        2.  + trip  -> TRIP
        3.  POI (,)-> POI
        4.  routing  -> ROUTING
        5.  -> POI
        """
        text = question.lower()

        # P1: NEARBY  - ()
        user_location_pattern = r"\b(i am at|i'm at|i'm in|at [A-Z]|in [A-Z])\b"
        has_user_location = bool(re.search(user_location_pattern, question))  # 

        nearby_keywords = [
            "near", "nearby", "around", "closest", "nearest", "within",
            "radius", "suggest", "recommend", "find", "where can",
            "something to eat", "to eat quickly"
        ]
        nearby_patterns = [r"what.*to eat", r"where.*can.*get", r"how many.*(near|around|within)"]
        has_nearby_keyword = any(keyword in text for keyword in nearby_keywords) or any(
            re.search(pattern, text) for pattern in nearby_patterns
        )

        # NEARBY : + nearby 
        # 
        multi_visit_pattern = r"visit.*,.*,|visit.*then|then.*visit"
        is_multi_visit = bool(re.search(multi_visit_pattern, text))

        if has_user_location and has_nearby_keyword and not is_multi_visit:
            return "nearby"

        # P2: TRIP  -  + /
        trip_keywords = [
            "trip", "itinerary", "schedule", "visit", "visiting",
            "best order", "optimal order", "organize", "arrange",
            "can i visit", "time budget", "hours available", "finish by",
            "latest departure", "what time should", "when will",
            "time will it take", "then go to", "then to", "first", "second", "third"
        ]

        # (visit A, B, C / visit...then...then)
        multi_location_pattern = r"visit.*,.*,|go.*to.*,.*to|visit.*then|then.*to|then go"
        has_multi_locations = bool(re.search(multi_location_pattern, text))

        # (hours available / finish by / start at)
        time_constraint_pattern = r"hours?\s+(available|to visit|can|able)|finish\s+by|start\s+(at|my)|time.*to|should.*leave|latest.*time|earliest.*time"
        has_time_constraints = bool(re.search(time_constraint_pattern, text))

        # Trip :
        # 1.  trip  + 
        # 2.  trip  + 
        # 3.  + 
        has_trip_keyword = any(keyword in text for keyword in trip_keywords)

        if (has_trip_keyword and (has_multi_locations or has_time_constraints)) or \
           (has_multi_locations and has_time_constraints):
            return "trip"

        # P3: POI ( NEARBY  "closest")
        # 3.1 : + "closest to each other"
        pair_comparison_pattern = r"(pair|pairs).*closest|closest.*to each other|which.*closest.*each other"
        if re.search(pair_comparison_pattern, text) and not has_user_location:
            return "poi"

        # 3.2 :"between A and B"()
        between_pattern = r"\bbetween\b.*\band\b"
        visit_pattern = r"\b(visit|go to|travel|drive)\b"
        if re.search(between_pattern, text) and not re.search(visit_pattern, text):
            return "poi"

        # P4: ROUTING ()
        routing_keywords = [
            "route", "directions", "direction", "navigate", "navigation",
            "how do i get", "distance from", "how far", "how long",
            "drive to", "walking from", "biking from", "after reaching", "where should i go next"
        ]
        routing_patterns = [r"take.*to.*drive", r"from .+ to .+", r"via .+"]
        if any(keyword in text for keyword in routing_keywords) or any(re.search(pattern, text) for pattern in routing_patterns):
            return "routing"

        # P5: POI (,,)
        return "poi"

class APIProcessor:
    """API """

    def __init__(self, google_client):
        self.google_client = google_client
        self.logger = logging.getLogger("spatial_agent.nodes.API")

    def _log_api_results(self, api_results: Dict[str, Any]) -> None:
        try:
            payload = json.dumps(api_results, ensure_ascii=False, default=str)
        except Exception as exc:
            payload = f"<failed to serialise api_results: {exc}>"
        self.logger.info("api_results snapshot: %s", payload)

    def nearby_search(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error") or not state.get("locations"):
            return state

        origin_location = state.get("origin_location")
        if origin_location and origin_location.lat is not None and origin_location.lng is not None:
            location = origin_location
        else:
            location = state["locations"][0]
            if not location.lat or not location.lng:
                state["error"] = f" {location.name} "
                self.logger.error("Nearby search aborted due to missing coordinates: %s", location.name)
                return state

        preferences = (state["parsed_info"].preferences or {}) if state.get("parsed_info") else {}
        keywords = preferences.get("keywords", [])
        min_rating = preferences.get("min_rating")

        place_type = None
        keyword = None
        if any(k in ["", "restaurant"] for k in keywords):
            place_type = "restaurant"
        elif keywords:
            keyword = keywords[0]

        self.logger.info(
            "Performing nearby search at (%s, %s) type=%s keyword=%s",
            location.lat,
            location.lng,
            place_type,
            keyword
        )

        results = self.google_client.nearby_search(
            location=(location.lat, location.lng),
            place_type=place_type,
            keyword=keyword,
            min_rating=min_rating
        )

        api_results = state.get("api_results") or {}
        api_results["nearby_places"] = results
        state["api_results"] = api_results
        self._log_api_results(api_results)
        self.logger.info("Nearby search returned %d results", len(results) if results else 0)
        return state

    def get_directions(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error") or len(state.get("locations", [])) < 2:
            return state

        locations = state["locations"]
        origin = locations[0]
        destination = locations[1]

        mode_map = {
            "driving": "driving",
            "walking": "walking",
            "transit": "transit",
            "cycling": "bicycling"
        }

        transport_mode = "driving"
        if state.get("parsed_info"):
            transport_mode = mode_map.get(state["parsed_info"].transportation_mode, "driving")

        origin_str = origin.address or origin.name
        dest_str = destination.address or destination.name

        if origin.lat is not None and origin.lng is not None:
            origin_str = f"{origin.lat},{origin.lng}"
        if destination.lat is not None and destination.lng is not None:
            dest_str = f"{destination.lat},{destination.lng}"

        self.logger.info(
            "Requesting directions. origin=%s destination=%s mode=%s",
            origin_str,
            dest_str,
            transport_mode
        )

        directions = self.google_client.get_directions(
            origin=origin_str,
            destination=dest_str,
            mode=transport_mode,
            alternatives=True
        )

        api_results = state.get("api_results") or {}
        api_results["directions"] = directions
        state["api_results"] = api_results
        self._log_api_results(api_results)

        has_steps = False
        if isinstance(directions, dict):
            primary = directions.get("primary") or {}
            has_steps = bool(primary.get("steps"))
        elif isinstance(directions, list):
            has_steps = any(route.get("steps") for route in directions)

        self.logger.info(
            "Directions retrieved. has_steps=%s route_count=%s",
            has_steps,
            len(directions.get("routes", [])) if isinstance(directions, dict) else 0
        )
        return state

    def get_place_details(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error") or not state.get("locations"):
            return state

        locations = state.get("locations", [])
        api_results = state.get("api_results") or {}
        origin = state.get("origin_location")
        search_location = None
        if origin and origin.lat is not None and origin.lng is not None:
            search_location = (origin.lat, origin.lng)

        details_by_name: Dict[str, Any] = api_results.get("place_details_by_name") or {}
        details_by_norm: Dict[str, Any] = api_results.get("place_details_by_norm") or {}

        for location in locations:
            norm = normalize_text(location.name)
            if norm in details_by_norm:
                continue

            details = None
            if location.place_id:
                self.logger.info("Fetching place details by place_id: %s", location.place_id)
                details = self.google_client.get_place_details(location.place_id)

            if not details:
                self.logger.info("Fallback to text search for location: %s", location.name)
                search_results = self.google_client.text_search(location.name, location=search_location, radius=20000)
                if search_results:
                    candidate = search_results[0]
                    place_id = candidate.get("place_id")
                    if place_id:
                        details = self.google_client.get_place_details(place_id)

            if details:
                entry = {
                    "name": details.get("name"),
                    "formatted_address": details.get("formatted_address"),
                    "rating": details.get("rating"),
                    "user_ratings_total": details.get("user_ratings_total"),
                    "price_level": details.get("price_level"),
                    "opening_hours": details.get("opening_hours"),
                    "place_id": details.get("place_id"),
                }
                details_by_name[location.name] = entry
                details_by_norm[norm] = entry

        if details_by_name:
            api_results["place_details_by_name"] = details_by_name
            api_results["place_details_by_norm"] = details_by_norm

        state["api_results"] = api_results
        self._log_api_results(api_results)
        return state

    def calculate_distances(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error") or len(state.get("locations", [])) < 2:
            return state

        locations = state["locations"]
        location_strings: List[str] = []

        for loc in locations:
            if loc.lat is not None and loc.lng is not None:
                location_strings.append(f"{loc.lat},{loc.lng}")
            else:
                location_strings.append(loc.name)

        mode_map = {
            "driving": "driving",
            "walking": "walking",
            "transit": "transit",
            "cycling": "bicycling"
        }

        transport_mode = "driving"
        if state.get("parsed_info"):
            transport_mode = mode_map.get(state["parsed_info"].transportation_mode, "driving")

        self.logger.info(
            "Requesting distance matrix. locations=%d mode=%s",
            len(location_strings),
            transport_mode
        )

        matrix = self.google_client.get_distance_matrix(
            origins=location_strings,
            destinations=location_strings,
            mode=transport_mode,
            format_output=True
        )

        api_results = state.get("api_results") or {}
        api_results["distance_matrix"] = matrix
        state["api_results"] = api_results
        self._log_api_results(api_results)
        self.logger.info("Distance matrix fetched: success=%s", bool(matrix))
        return state


class OptimizationProcessor:
    """"""

    def __init__(self):
        from ..utils.optimization import TripOptimizer

        self.optimizer = TripOptimizer()
        self.logger = logging.getLogger("spatial_agent.nodes.Optimization")

    def optimize_trip(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error"):
            return state

        api_results = state.get("api_results") or {}
        distance_matrix = api_results.get("distance_matrix")
        if not distance_matrix:
            self.logger.warning("Distance matrix missing. Skipping optimization.")
            return state

        locations = state.get("locations", [])
        parsed_info = state.get("parsed_info")
        if parsed_info is None:
            self.logger.warning("Parsed info missing. Skipping optimization.")
            return state

        location_names = [loc.name for loc in locations]
        start_idx = 0
        if parsed_info.start_location:
            for i, name in enumerate(location_names):
                if name == parsed_info.start_location:
                    start_idx = i
                    break

        optimization_result = self.optimizer.optimize_trip(
            distance_matrix=distance_matrix,
            location_names=location_names,
            visit_durations=parsed_info.visit_durations,
            start_location_idx=start_idx,
            total_time_available=parsed_info.total_time_available,
            start_time=parsed_info.start_time
        )

        calculations = state.get("calculations") or {}
        calculations["optimization"] = optimization_result
        state["calculations"] = calculations
        self.logger.info(
            "Optimization completed. feasible=%s total_time=%s",
            optimization_result.get("feasible"),
            optimization_result.get("total_time_seconds")
        )
        return state


class DirectionProcessor:
    """"""

    def __init__(self):
        self.logger = logging.getLogger("spatial_agent.nodes.Direction")

    def compute_direction(self, state: SpatialAgentState) -> SpatialAgentState:
        if state.get("error"):
            return state

        locations = state.get("locations") or []
        if not locations:
            self.logger.warning("Direction computation skipped: no locations available")
            return state

        parsed_info = state.get("parsed_info")
        origin = self._resolve_origin(state, parsed_info, locations)
        target = self._resolve_target(parsed_info, locations, origin)

        if not origin or origin.lat is None or origin.lng is None:
            self.logger.warning("Direction computation skipped: missing origin coordinates")
            return state

        if not target or target.lat is None or target.lng is None:
            self.logger.warning("Direction computation skipped: missing target coordinates")
            return state

        bearing = self._compute_bearing(origin.lat, origin.lng, target.lat, target.lng)
        distance_km = self._compute_distance_km(origin.lat, origin.lng, target.lat, target.lng)
        primary_direction = self._bearing_to_direction(bearing)
        simple_direction = self._bearing_to_direction(bearing, segments=8)

        calculations = state.get("calculations") or {}
        calculations["direction"] = {
            "origin": {
                "name": origin.name,
                "lat": origin.lat,
                "lng": origin.lng,
            },
            "target": {
                "name": target.name,
                "lat": target.lat,
                "lng": target.lng,
            },
            "bearing": bearing,
            "direction": primary_direction,
            "simple_direction": simple_direction,
            "distance_km": distance_km,
            "distance_meters": distance_km * 1000,
        }
        state["calculations"] = calculations
        self.logger.info(
            "Direction computed. origin=%s target=%s bearing=%.2f direction=%s distance_km=%.3f",
            origin.name,
            target.name,
            bearing,
            primary_direction,
            distance_km
        )
        return state

    def _resolve_origin(
        self,
        state: SpatialAgentState,
        parsed_info: Optional[ParsedInfo],
        locations: List[Location]
    ) -> Optional[Location]:
        origin = state.get("origin_location")
        if parsed_info and parsed_info.start_location:
            matched = self._find_location(locations, parsed_info.start_location)
            if matched:
                origin = matched
        if origin is None and locations:
            origin = locations[0]
        return origin

    def _resolve_target(
        self,
        parsed_info: Optional[ParsedInfo],
        locations: List[Location],
        origin: Optional[Location]
    ) -> Optional[Location]:
        if parsed_info and parsed_info.locations:
            for name in parsed_info.locations:
                candidate = self._find_location(locations, name)
                if not candidate:
                    continue
                if origin and normalize_text(candidate.name) == normalize_text(origin.name):
                    continue
                return candidate

        for loc in locations:
            if origin and normalize_text(loc.name) == normalize_text(origin.name):
                continue
            if loc.lat is not None and loc.lng is not None:
                return loc
        return None

    def _find_location(self, locations: List[Location], name: Optional[str]) -> Optional[Location]:
        if not name:
            return None
        target_norm = normalize_text(name)
        for loc in locations:
            if normalize_text(loc.name) == target_norm:
                return loc
        return None

    def _compute_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)

        y = math.sin(delta_lambda) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
        return (math.degrees(math.atan2(y, x)) + 360) % 360

    def _bearing_to_direction(self, bearing: float, segments: int = 16) -> str:
        if segments == 8:
            sequence = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        elif segments == 4:
            sequence = ["N", "E", "S", "W"]
        else:
            sequence = PRIMARY_DIRECTIONS

        step = 360.0 / len(sequence)
        index = int((bearing + step / 2) // step) % len(sequence)
        return sequence[index]

    def _compute_distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c

class AnswerGenerator:
    """"""

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        self.logger = logging.getLogger("spatial_agent.nodes.Answer")

    def generate_answer(self, state: SpatialAgentState) -> SpatialAgentState:
        # 
        self.logger.info("=" * 80)
        self.logger.info("[GENERATE] Starting Generate Phase - Natural Language Answer Generation")
        self.logger.info("=" * 80)

        if state.get("error"):
            state["final_answer"] = f",:{state['error']}"
            return state

        #  measure type  intent  ()
        transformation_plan = state.get("transformation_plan")
        measure_type = transformation_plan.measure if transformation_plan else None

        #  measure_type, intent
        if not measure_type:
            intent = state.get("intent")
            # Intent  measure 
            measure_type = {
                "nearby": "nearest",
                "routing": "route",
                "trip": "order",
                "poi": "attribute"
            }.get(intent, "unknown")

        api_results = state.get("api_results", {})
        calculations = state.get("calculations", {})

        try:
            options = state.get("options") or []
            predicted_idx = state.get("predicted_option")
            evaluation = state.get("evaluation") or {}

            #  :, evaluation 
            if options and isinstance(predicted_idx, int) and 0 <= predicted_idx < len(options):
                reason = evaluation.get("reason")
                if not reason and isinstance(evaluation.get("fallback"), dict):
                    reason = evaluation["fallback"].get("reason")

                # ,
                answer = f"** ( {predicted_idx}):** {options[predicted_idx]}"
                if reason:
                    answer = f"{reason}\n\n{answer}"
            else:
                # : measure type 
                if measure_type == "nearest":
                    answer = self._generate_nearby_answer(api_results)
                elif measure_type == "route":
                    answer = self._generate_routing_answer(api_results)
                elif measure_type == "order":
                    answer = self._generate_trip_answer(calculations)
                elif measure_type in ["bearing", "distance", "attribute"]:
                    answer = self._generate_poi_answer(api_results, calculations)
                else:
                    answer = ",."

            state["final_answer"] = answer
            self.logger.info(
                "Generated answer. measure_type=%s length=%d",
                measure_type,
                len(answer)
            )
        except Exception as exc:
            state["final_answer"] = f":{exc}"
            self.logger.exception("Answer generation failed")

        return state

    def _generate_nearby_answer(self, api_results: Dict[str, Any]) -> str:
        nearby_places = api_results.get("nearby_places", [])
        if not nearby_places:
            return ",."

        best_place = nearby_places[0]
        answer = f", **{best_place['name']}**"

        if best_place.get("rating"):
            answer += f", {best_place['rating']}"
            if best_place.get("user_ratings_total"):
                answer += f" ({best_place['user_ratings_total']} )"

        if best_place.get("vicinity"):
            answer += f",:{best_place['vicinity']}"

        if len(nearby_places) > 1:
            other_places = [place.get("name") for place in nearby_places[1:3] if place.get("name")]
            if other_places:
                answer += f"\n\n:{', '.join(other_places)}"

        return answer

    def _generate_routing_answer(self, api_results: Dict[str, Any]) -> str:
        directions_data = api_results.get("directions")
        if not directions_data:
            return ",."

        if isinstance(directions_data, dict):
            primary = directions_data.get("primary") or directions_data
            alternatives = directions_data.get("routes", [primary])
        else:
            primary = directions_data
            alternatives = [primary]

        if not primary:
            return ",."

        answer = "**:**\n"
        answer += f"- :{primary.get('distance_text')}\n"
        answer += f"- :{primary.get('duration_text')}\n"
        answer += f"- :{primary.get('start_address')}\n"
        answer += f"- :{primary.get('end_address')}\n\n"

        answer += "**:**\n"
        for i, step in enumerate((primary.get("steps") or [])[:5], 1):
            instruction = step.get("html_instructions", "")
            instruction = instruction.replace("<b>", "").replace("</b>", "")
            instruction = instruction.replace('<div style="font-size:0.9em">', ' ').replace('</div>', '')
            answer += f"{i}. {instruction} ({step.get('distance')})\n"

        total_steps = len(primary.get("steps", []))
        if total_steps > 5:
            answer += f"...  {total_steps - 5} "

        if len(alternatives) > 1:
            answer += "\n\n**:**"
            for idx, route in enumerate(alternatives[1:], start=2):
                answer += (
                    f"\n-  {idx}: {route.get('summary') or ''} | "
                    f" {route.get('distance_text')} |  {route.get('duration_text')}"
                )

        return answer

    def _generate_trip_answer(self, calculations: Dict[str, Any]) -> str:
        optimization = calculations.get("optimization", {})
        if optimization.get("error"):
            return f":{optimization['error']}"
        if not optimization.get("feasible"):
            return "."

        answer = "**:**\n\n"
        for idx, location in enumerate(optimization.get("location_order", []), start=1):
            answer += f"{idx}. {location}\n"

        total_time_seconds = optimization.get("total_time_seconds", 0)
        answer += f"\n**:** {total_time_seconds / 3600:.1f} "

        if optimization.get("total_distance_text"):
            answer += f"\n**:** {optimization['total_distance_text']}"

        if optimization.get("time_constraint_violated"):
            suggestion = optimization.get("suggestion", "")
            answer += f"\n\nWARNING **:** {suggestion}"

        if optimization.get("estimated_end_time"):
            answer += f"\n**:** {optimization['estimated_end_time']}"

        route_details = optimization.get("route_details", [])
        if route_details:
            answer += "\n\n**:**\n"
            for detail in route_details:
                answer += (
                    f"- {detail['from']} -> {detail['to']}: "
                    f"{detail['duration_text']} ({detail['distance_text']})\n"
                )

        return answer

    def _generate_poi_answer(self, api_results: Dict[str, Any], calculations: Dict[str, Any]) -> str:
        place_details = api_results.get("place_details")
        search_results = api_results.get("search_results", [])
        direction_info = (calculations or {}).get("direction") if calculations else None

        if place_details:
            place = place_details
            answer = f"**{place['name']}**\n\n"

            if place.get("formatted_address"):
                answer += f" **:** {place['formatted_address']}\n"

            if place.get("rating"):
                answer += f" **:** {place['rating']}"
                if place.get("user_ratings_total"):
                    answer += f" ({place['user_ratings_total']} )"
                answer += "\n"

            if place.get("formatted_phone_number"):
                answer += f" **:** {place['formatted_phone_number']}\n"

            if place.get("website"):
                answer += f" **:** {place['website']}\n"

            opening_hours = place.get("opening_hours")
            if opening_hours and opening_hours.get("weekday_text"):
                answer += "\n**:**\n"
                for day in opening_hours["weekday_text"]:
                    answer += f"- {day}\n"

            return answer

        if search_results:
            place = search_results[0]
            answer = f":**{place.get('name', '')}**\n\n"
            answer += f" **:** {place.get('formatted_address', '')}\n"
            if place.get("rating"):
                answer += f" **:** {place['rating']}\n"
            direction_text = self._format_direction_answer(direction_info)
            if direction_text:
                answer += f"\n{direction_text}"
            return answer

        direction_text = self._format_direction_answer(direction_info)
        if direction_text:
            return direction_text

        return ",."

    def _format_direction_answer(self, direction_info: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(direction_info, dict):
            return None

        origin = (direction_info.get("origin") or {}).get("name")
        target = (direction_info.get("target") or {}).get("name")
        direction = direction_info.get("simple_direction") or direction_info.get("direction")
        bearing = direction_info.get("bearing")
        distance_km = direction_info.get("distance_km")

        if direction is None and distance_km is None:
            return None

        parts: List[str] = []
        if origin and target:
            parts.append(f" {origin}  {target}")
        if direction is not None:
            text = f" {direction}"
            if bearing is not None:
                text += f" ( {bearing:.1f} degrees )"
            parts.append(text)
        if distance_km is not None:
            parts.append(f" {distance_km:.2f} ")

        return ",".join(parts) if parts else None
