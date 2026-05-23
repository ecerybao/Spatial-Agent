"""
 -  DAG 

:
1.  TransformationPlan  DAG
2. 
3. 
4. ,
5. 
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .state import SpatialAgentState, TransformationPlan, TransformationStep
from .operators import OPERATOR_REGISTRY, get_operator
from ..tools.google_maps import GoogleMapsClient
from ..utils.optimization import haversine
from ..utils.logging_utils import log_dag_flow, log_comparison, format_data_summary
from ..utils.logging_formatter import LogFormatter

logger = logging.getLogger("spatial_agent.executors")


def _resolve_concept_reference(concept_id: str, inputs: Dict[str, Any], intermediate_concepts: Dict[str, Any]) -> Any:
    """
    , 'coords_options[0]'

    Args:
        concept_id: ID, 'coords_options[0]'
        inputs: 
        intermediate_concepts: 

    Returns:
        
    """
    import re

    # 
    result = inputs.get(concept_id) or intermediate_concepts.get(concept_id)
    if result is not None:
        return result

    # : name[index]
    match = re.match(r'^(\w+)\[(\d+)\]$', concept_id)
    if match:
        base_name = match.group(1)
        index = int(match.group(2))

        # 
        base_array = inputs.get(base_name) or intermediate_concepts.get(base_name)

        if isinstance(base_array, list) and 0 <= index < len(base_array):
            logger.debug(f"[resolve_concept] : {concept_id} -> {base_name}[{index}]")
            return base_array[index]
        else:
            logger.warning(f"[resolve_concept] : {concept_id}, base_array type={type(base_array)}, len={len(base_array) if isinstance(base_array, list) else 'N/A'}")

    return None


def _extract_coordinates_from_concept(concept_data: Any) -> tuple[Optional[float], Optional[float]]:
    """
     (lat, lng)

    :
    1. geocode  {'origin_location': Location}  {'locations': [Location]}
    2.  {'lat': ..., 'lng': ...}

    Returns:
        (lat, lng) , (None, None)
    """
    if not concept_data or not isinstance(concept_data, dict):
        return None, None

    # 1: geocode 
    if 'origin_location' in concept_data:
        loc = concept_data['origin_location']
        if hasattr(loc, 'lat') and hasattr(loc, 'lng'):
            return loc.lat, loc.lng
    elif 'locations' in concept_data and concept_data['locations']:
        loc = concept_data['locations'][0]
        if hasattr(loc, 'lat') and hasattr(loc, 'lng'):
            return loc.lat, loc.lng

    # 2: 
    if 'lat' in concept_data and 'lng' in concept_data:
        return concept_data['lat'], concept_data['lng']

    return None, None


class TransformationExecutor:
    """
    

     TransformationPlan  DAG ,
    """

    def __init__(self, google_client: GoogleMapsClient):
        self.client = google_client
        self.operators = OPERATOR_REGISTRY

    def execute(self, state: SpatialAgentState) -> SpatialAgentState:
        """
        

        Args:
            state: ( transformation_plan)

        Returns:
            ( intermediate_concepts  concept_flow)
        """
        if state.get("error"):
            return state

        plan = state.get("transformation_plan")
        if not plan:
            logger.error("[TransformationExecutor] ")
            state["error"] = ""
            return state

        logger.info(f"[TransformationExecutor] : {len(plan.transformations)} ")

        #  intent,
        current_intent = state.get("intent")
        if current_intent:
            from ..tools.local_context_db import ContextManager
            ContextManager.set_current_intent(current_intent)
            logger.info(f"[TransformationExecutor]  intent: {current_intent}, : {'' if ContextManager.should_use_local_db() else ''}")

        # 
        intermediate_concepts: Dict[str, Any] = {}
        concept_flow: List[Dict[str, Any]] = []

        # : 
        for entity in plan.types:
            # 
            concept_id = f"{entity.concept_type.value if entity.concept_type else 'unknown'}_{entity.name}"
            intermediate_concepts[concept_id] = {
                'name': entity.name,
                'type': entity.concept_type.value if entity.concept_type else None,
                'role': entity.functional_role.value if entity.functional_role else None,
                'attributes': entity.attributes
            }

        # 
        try:
            for i, step in enumerate(plan.transformations):
                logger.info(f"[TransformationExecutor]  {i+1}/{len(plan.transformations)}: {step.operator}")
                logger.info(f"  : {step.before}")
                logger.info(f"  : {step.after}")
                logger.info(f"  : {format_data_summary(step.params, max_length=200, logger_level=logger.level)}")

                # 
                operator_func = get_operator(step.operator)
                if not operator_func:
                    logger.error(f"[TransformationExecutor] : {step.operator}")
                    state["error"] = f": {step.operator}"
                    return state

                # 
                inputs = self._prepare_inputs(step, intermediate_concepts, plan, state)
                if inputs is None:
                    logger.error(f"[TransformationExecutor] : {step.operator}")
                    state["error"] = f": {step.operator}"
                    return state

                # (client, state)
                inputs_summary = {
                    k: v for k, v in inputs.items()
                    if k not in ['client', 'state']
                }
                #  Location ,
                for key, value in list(inputs_summary.items()):
                    if hasattr(value, '__class__') and value.__class__.__name__ == 'Location':
                        inputs_summary[key] = f"{value.name} ({value.lat:.4f}, {value.lng:.4f})"

                logger.info(f"  : {format_data_summary(inputs_summary, max_length=300, logger_level=logger.level)}")

                # 
                try:
                    outputs = self._execute_operator(operator_func, step, inputs, plan, intermediate_concepts)
                    logger.info(f"  : {format_data_summary(outputs, max_length=200, logger_level=logger.level)}")

                except Exception as e:
                    logger.exception(f"[TransformationExecutor] : {step.operator}")
                    state["error"] = f": {step.operator} - {str(e)}"
                    return state

                # 
                self._store_outputs(step, outputs, intermediate_concepts)

                #  intermediate_concepts 
                logger.info(f"   intermediate_concepts:")
                for concept_id in step.after:
                    if concept_id in intermediate_concepts:
                        value = intermediate_concepts[concept_id]
                        logger.info(f"    {concept_id} = {format_data_summary(value, max_length=300, logger_level=logger.level)}")

                # 
                concept_flow.append({
                    'step': i + 1,
                    'operator': step.operator,
                    'before': step.before,
                    'after': step.after,
                    'description': step.description or f"{step.before} -> [{step.operator}] -> {step.after}",
                    'output_summary': self._summarize_output(outputs)
                })

            # 
            state["intermediate_concepts"] = intermediate_concepts
            state["concept_flow"] = concept_flow

            # ( DAG )
            logger.info(f"[TransformationExecutor] :")
            log_dag_flow(logger, concept_flow)

            logger.info(f"[TransformationExecutor] ,  {len(concept_flow)} ")

            #  : geocoded_origin  option_X,
            if "geocoded_origin" in intermediate_concepts:
                origin_data = intermediate_concepts["geocoded_origin"]
                if isinstance(origin_data, dict) and 'origin_location' in origin_data:
                    origin = origin_data['origin_location']
                    if hasattr(origin, 'lat') and hasattr(origin, 'lng') and origin.lat and origin.lng:
                        #  option_X 
                        option_ids = sorted([k for k in intermediate_concepts.keys() if k.startswith('option_')])
                        if option_ids:
                            option_distances = {}
                            option_names = []
                            distance_values = []

                            logger.info(f"[Auto Distance]  {len(option_ids)} ")

                            for option_id in option_ids:
                                option_data = intermediate_concepts[option_id]
                                if isinstance(option_data, dict) and 'locations' in option_data:
                                    option_loc = option_data['locations'][0] if option_data['locations'] else None
                                    if option_loc and hasattr(option_loc, 'lat') and hasattr(option_loc, 'lng'):
                                        if option_loc.lat and option_loc.lng:
                                            # ()
                                            distance_m = haversine(
                                                origin.lat, origin.lng,
                                                option_loc.lat, option_loc.lng
                                            )
                                            option_distances[option_id] = {
                                                'name': option_loc.name,
                                                'distance_m': distance_m,
                                                'distance_km': distance_m / 1000
                                            }
                                            option_names.append(option_loc.name)
                                            distance_values.append(distance_m / 1000)  # km

                            if option_distances:
                                # ()
                                min_index = distance_values.index(min(distance_values)) if distance_values else None
                                log_comparison(
                                    logger,
                                    options=option_names,
                                    values=distance_values,
                                    labels=[f"{v:.2f} km" for v in distance_values],
                                    highlight_index=min_index,
                                    show_bar_chart=True
                                )
                                logger.info(f"[Auto Distance]  {len(option_distances)} ()")

        except Exception as e:
            logger.exception(f"[TransformationExecutor] ")
            state["error"] = f": {str(e)}"
        finally:
            #  intent
            if current_intent:
                from ..tools.local_context_db import ContextManager
                ContextManager.clear_current_intent()

        return state

    def _prepare_inputs(
        self,
        step: TransformationStep,
        intermediate_concepts: Dict[str, Any],
        plan: TransformationPlan,
        state: SpatialAgentState
    ) -> Optional[Dict[str, Any]]:
        """
        

         intermediate_concepts 

        Args:
            step: 
            intermediate_concepts: 
            plan: 
            state: 

        Returns:
              None()
        """
        inputs = {
            'client': self.client,
            'state': state,
        }

        #  before 
        for concept_id in step.before:
            if concept_id in intermediate_concepts:
                inputs[concept_id] = intermediate_concepts[concept_id]
            else:
                logger.debug(f"[prepare_inputs]  {concept_id}  intermediate_concepts")

        # 
        inputs['params'] = {**plan.params, **step.params}
        inputs['mode'] = plan.mode

        #  : geocode  params  text, concept ID 
        if step.operator == "geocode" and not inputs['params'].get("text"):
            text = self._extract_text_from_concept_id(step, plan, state)
            if text:
                inputs['params']["text"] = text
                logger.info(f"[prepare_inputs]  concept ID  text: {text}")

        return inputs

    def _infer_id_from_name(self, name: str) -> str:
        """
         concept ID

        : "The Rimrock Resort Hotel" -> "location_hotel"

        Args:
            name: 

        Returns:
             concept ID
        """
        # :()
        import re
        words = re.findall(r'\w+', name.lower())
        if words:
            key_word = words[-1]  # 
            return f"location_{key_word}"
        return "unknown"

    def _parse_time_string(self, time_str: str) -> str:
        """
         24 

        :
        - "9:00 AM" -> "09:00"
        - "9:00 AM Sunday" -> "09:00"
        - "3:30 PM" -> "15:30"
        - "09:00" -> "09:00"

        Args:
            time_str: 

        Returns:
            24  "HH:MM"
        """
        from datetime import datetime
        import re

        # :
        time_str = time_str.strip()
        time_str = re.sub(r'\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)', '', time_str, flags=re.IGNORECASE)

        # 
        formats = [
            "%I:%M %p",      # 12-hour format with AM/PM (e.g., "9:00 AM")
            "%H:%M",         # 24-hour format (e.g., "09:00")
            "%I %p",         # Hour only with AM/PM (e.g., "9 AM")
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(time_str.strip(), fmt)
                return dt.strftime("%H:%M")
            except ValueError:
                continue

        # ,
        logger.warning(f"[parse_time_string] : {time_str},  09:00")
        return "09:00"

    def _build_datetime_from_params(self, time_str: str, day_str: str) -> 'datetime':
        """
         datetime 

        Args:
            time_str: , "5:00 PM", "17:00"
            day_str: , "Saturday"

        Returns:
            datetime ()
        """
        from datetime import datetime, timedelta

        # 
        time_24h = self._parse_time_string(time_str)
        hour, minute = map(int, time_24h.split(':'))

        # 
        day_map = {
            'sunday': 6, 'monday': 0, 'tuesday': 1, 'wednesday': 2,
            'thursday': 3, 'friday': 4, 'saturday': 5
        }
        target_weekday = day_map.get(day_str.lower(), 0)

        # 
        today = datetime.now()
        days_ahead = target_weekday - today.weekday()
        if days_ahead < 0:
            days_ahead += 7

        target_date = today + timedelta(days=days_ahead)
        return target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _extract_visit_durations_from_question(
        self,
        question: str,
        locations: List[Dict]
    ) -> Optional[Dict[str, float]]:
        """
        

        :
            "I want to visit the Senso-ji Temple for 1 hour, Shibuya Crossing for 1.5 hours,
             Ueno Park for 2 hours, and the Tokyo Skytree for 1.5 hours."

        Args:
            question: 
            locations: ( name )

        Returns:
            {: ()}  None
        """
        import re

        if not question or not locations:
            return None

        #  :  " for X hours" 
        #  locations 

        #  "PLACE for X hours" 
        # : "visit the Sagrada Familia for 2 hours"
        place_duration_pattern = r'(?:visit\s+(?:the\s+)?|go\s+to\s+)?([\w\s\-\'aeiouun]+?)\s+for\s+(\d+\.?\d*)\s*hours?'

        question_durations = {}
        for match in re.finditer(place_duration_pattern, question, re.IGNORECASE):
            place_name = match.group(1).strip()
            duration = float(match.group(2))
            question_durations[place_name.lower()] = duration
            logger.debug(f"[extract_visit_durations] : '{place_name}' = {duration}h")

        if not question_durations:
            return None

        #  locations 
        durations = {}
        location_names = []
        for loc in locations:
            if isinstance(loc, dict):
                name = loc.get('name', '')
            else:
                name = str(loc) if loc else ''
            if name:
                location_names.append(name)

        for loc_name in location_names:
            # 
            matched_duration = None

            # 1: 
            loc_lower = loc_name.lower()
            for q_place, duration in question_durations.items():
                if q_place in loc_lower or loc_lower in q_place:
                    matched_duration = duration
                    break

            # 2: 
            if matched_duration is None:
                # ()
                keywords = loc_name.split(',')[0].strip().lower()
                #  "Basilica de la", "Temple of" 
                keywords = re.sub(r'^(basilica de la|temple of|the|park)\s*', '', keywords, flags=re.IGNORECASE)

                for q_place, duration in question_durations.items():
                    if keywords in q_place or q_place in keywords:
                        matched_duration = duration
                        break
                    # 
                    for word in keywords.split():
                        if len(word) > 3 and word in q_place:
                            matched_duration = duration
                            break
                    if matched_duration:
                        break

            if matched_duration is not None:
                durations[loc_name] = matched_duration

        if durations:
            logger.info(f"[extract_visit_durations] : {durations}")
            return durations

        return None

    def _extract_text_from_concept_id(
        self,
        step: TransformationStep,
        plan: TransformationPlan,
        state: SpatialAgentState
    ) -> Optional[str]:
        """
         concept ID ()

        ():
        1. :concept_id == entity.id
        2. :(origin/destination/home)-> extent/condition 
        3. : ID 
        4.  options ( concept_id  option_N )
        5.  step.description 
        6. ( origin/home )

        Args:
            step: 
            plan: 
            state: 

        Returns:
            , None
        """
        if not step.before:
            return None

        import re
        concept_entities = plan.types if hasattr(plan, 'types') else []

        for concept_id in step.before:
            #  1:  entity.id
            for entity in concept_entities:
                if isinstance(entity, dict):
                    entity_id = entity.get('id')
                    name = entity.get('name')
                    role = entity.get('role', 'support')
                else:
                    entity_id = getattr(entity, 'id', None)
                    name = entity.name
                    role = entity.functional_role.value if hasattr(entity.functional_role, 'value') else str(entity.functional_role)

                if entity_id == concept_id and name:
                    logger.info(f"[extract_text] 1-: {concept_id} -> {name}")
                    return name

            #  2: 
            semantic_mapping = {
                'origin': ['extent', 'start', 'from', 'departure', 'current_location'],
                'destination': ['extent', 'condition', 'end', 'to', 'arrival', 'target'],
                'home': ['extent', 'home', 'house', 'residence'],
                'hotel': ['extent', 'condition', 'accommodation', 'lodging'],
                'hostel': ['extent', 'condition', 'accommodation', 'lodging'],
                'start': ['extent', 'start', 'beginning'],
                'end': ['extent', 'condition', 'finish', 'final'],
            }

            concept_lower = concept_id.lower()
            for generic_word, role_keywords in semantic_mapping.items():
                if concept_lower == generic_word or generic_word in concept_lower:
                    logger.info(f"[extract_text] : {concept_id} ({generic_word})")

                    #  extent 
                    for entity in concept_entities:
                        if isinstance(entity, dict):
                            name = entity.get('name')
                            role = entity.get('role', 'support')
                        else:
                            name = entity.name
                            role = entity.functional_role.value if hasattr(entity.functional_role, 'value') else str(entity.functional_role)

                        # 
                        if role in ['extent', 'temporal_extent'] or any(kw in role for kw in role_keywords):
                            if name:
                                logger.info(f"[extract_text] 2-: {concept_id} -> {name} (role={role})")
                                return name

                    #  extent, condition 
                    if generic_word in ['destination', 'hotel', 'hostel', 'end']:
                        for entity in concept_entities:
                            if isinstance(entity, dict):
                                name = entity.get('name')
                                role = entity.get('role', 'support')
                            else:
                                name = entity.name
                                role = entity.functional_role.value if hasattr(entity.functional_role, 'value') else str(entity.functional_role)

                            if role == 'condition' and name:
                                logger.info(f"[extract_text] 2-(condition): {concept_id} -> {name}")
                                return name

            #  3: 
            for entity in concept_entities:
                if isinstance(entity, dict):
                    name = entity.get('name')
                else:
                    name = entity.name

                if name:
                    inferred_id = self._infer_id_from_name(name)
                    if inferred_id == concept_id:
                        logger.info(f"[extract_text] 3-: {concept_id} -> {name}")
                        return name

            #  4: option_N 
            if concept_id.startswith('option_'):
                try:
                    idx = int(concept_id.split('_')[1])
                    options = state.get('options', [])
                    if 0 <= idx < len(options):
                        option_text = options[idx]
                        logger.info(f"[extract_text] 4-: {concept_id} -> {option_text}")
                        return option_text
                except (ValueError, IndexError) as e:
                    logger.debug(f"[extract_text]  option index : {e}")

            #  5:  description 
            if step.description:
                match = re.search(r'["\']([^"\']+)["\']', step.description)
                if match:
                    text = match.group(1)
                    logger.info(f"[extract_text] 5-description: {concept_id} -> {text}")
                    return text

            #  6: ( origin/home/start)
            if concept_id in ['origin', 'home', 'start', 'current_location', 'my_location']:
                question = state.get('question', '')
                #  "I'm at X", "from X", "starting at X", "at X"
                patterns = [
                    r"(?:I'm at|I am at|at)\s+([^,\.!?]+)",
                    r"(?:from|starting (?:at|from))\s+([^,\.!?]+)",
                    r"(?:leaving|departing) (?:from\s+)?([^,\.!?]+)",
                ]
                for pattern in patterns:
                    match = re.search(pattern, question, re.IGNORECASE)
                    if match:
                        location_text = match.group(1).strip()
                        #  "the" 
                        location_text = re.sub(r'^(?:the|a|an)\s+', '', location_text, flags=re.IGNORECASE)
                        logger.info(f"[extract_text] 6-: {concept_id} -> {location_text}")
                        return location_text

        return None

    def _execute_operator(
        self,
        operator_func,
        step: TransformationStep,
        inputs: Dict[str, Any],
        plan: TransformationPlan,
        intermediate_concepts: Dict[str, Any] = None
    ) -> Any:
        """
        

        
        """
        operator_name = step.operator
        client = inputs['client']
        params = inputs.get('params', {})
        if intermediate_concepts is None:
            intermediate_concepts = {}

        # ( client)
        if operator_name == 'query_local_place':
            #  params  step.before 
            place_name = params.get('place_name')
            logger.info(f"[query_local_place] step.before={step.before}, params={params}")
            if not place_name:
                #  1:  inputs 
                for concept_id in step.before:
                    if concept_id in inputs:
                        data = inputs[concept_id]
                        if isinstance(data, dict):
                            place_name = data.get('name') or data.get('place_name', '')
                        elif isinstance(data, str):
                            place_name = data
                        if place_name:
                            logger.debug(f"[query_local_place] 1: {concept_id} -> {place_name}")
                            break
                #  2:  plan.types  name( concept_id  name)
                if not place_name:
                    logger.info(f"[query_local_place] 2, plan.types: {hasattr(plan, 'types')}, : {len(plan.types) if hasattr(plan, 'types') and plan.types else 0}")
                    if hasattr(plan, 'types') and plan.types:
                        for concept_id in step.before:
                            #  concept_id 
                            # : "location_Brassica" -> ["location", "brassica"]
                            # : "location_AraucanoPark" -> ["location", "araucano", "park"]
                            import re
                            # 
                            parts = concept_id.replace('_', ' ').split()
                            #  CamelCase ( "AraucanoPark" -> "Araucano Park")
                            concept_keywords = []
                            for part in parts:
                                # ,
                                camel_split = re.sub(r'([A-Z])', r' \1', part).split()
                                concept_keywords.extend([w.lower() for w in camel_split if w])
                            logger.debug(f"[query_local_place] concept_keywords={concept_keywords}")

                            for entity in plan.types:
                                entity_id = entity.get('id') if isinstance(entity, dict) else getattr(entity, 'id', None)
                                entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)
                                logger.info(f"[query_local_place] : concept_id={concept_id}, entity_id={entity_id}, entity_name={entity_name}")

                                #  1:  entity_id
                                if entity_id == concept_id and entity_name:
                                    place_name = entity_name
                                    logger.info(f"[query_local_place] ID: {concept_id} -> {place_name}")
                                    break

                                #  2: concept_id  entity_name 
                                if entity_name:
                                    entity_name_lower = entity_name.lower()
                                    for kw in concept_keywords:
                                        if kw != 'location' and kw in entity_name_lower:
                                            place_name = entity_name
                                            logger.info(f"[query_local_place] : {concept_id} ({kw}) -> {place_name}")
                                            break
                                    if place_name:
                                        break

                            if place_name:
                                break
            if place_name:
                result = operator_func(place_name)

                #   Google Maps
                if result is None:
                    logger.info(f"[query_local_place]  '{place_name}', Google Maps")
                    try:
                        from src.agent.operators import geocode as geocode_op, place_details as place_details_op

                        #  geocode  place_id
                        geocoded = geocode_op(client, place_name)
                        if geocoded and geocoded.get('place_id'):
                            # 
                            details = place_details_op(client, geocoded['place_id'])
                            if details:
                                # 
                                details['from_google_fallback'] = True
                                details['local_db_name'] = place_name
                                logger.info(f"[query_local_place] OK Google : {place_name}")
                                return details
                    except Exception as e:
                        logger.warning(f"[query_local_place] Google : {e}")

                return result

            logger.warning(f"[query_local_place] , step.before={step.before}")
            return None

        elif operator_name == 'query_local_places_batch':
            #  params  step.before 
            place_names = params.get('place_names')
            if not place_names and step.before:
                # step.before 
                place_names = step.before
            if place_names:
                return operator_func(place_names)
            return []

        elif operator_name == 'query_local_coordinates':
            #  params  step.before 
            place_name = params.get('place_name')
            logger.info(f"[query_local_coordinates] step.before={step.before}, params={params}")
            if not place_name:
                #  1:  inputs 
                for concept_id in step.before:
                    if concept_id in inputs:
                        data = inputs[concept_id]
                        if isinstance(data, dict):
                            place_name = data.get('name') or data.get('place_name', '')
                        elif isinstance(data, str):
                            place_name = data
                        if place_name:
                            logger.debug(f"[query_local_coordinates] 1: {concept_id} -> {place_name}")
                            break
                #  2:  plan.types  name
                if not place_name:
                    if hasattr(plan, 'types') and plan.types:
                        for concept_id in step.before:
                            import re
                            parts = concept_id.replace('_', ' ').split()
                            concept_keywords = []
                            for part in parts:
                                camel_split = re.sub(r'([A-Z])', r' \1', part).split()
                                concept_keywords.extend([w.lower() for w in camel_split if w])

                            for entity in plan.types:
                                entity_id = entity.get('id') if isinstance(entity, dict) else getattr(entity, 'id', None)
                                entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)

                                if entity_id == concept_id and entity_name:
                                    place_name = entity_name
                                    logger.info(f"[query_local_coordinates] ID: {concept_id} -> {place_name}")
                                    break

                                if entity_name:
                                    entity_name_lower = entity_name.lower()
                                    for kw in concept_keywords:
                                        if kw != 'location' and kw in entity_name_lower:
                                            place_name = entity_name
                                            logger.info(f"[query_local_coordinates] : {concept_id} ({kw}) -> {place_name}")
                                            break
                                    if place_name:
                                        break
                            if place_name:
                                break
            if place_name:
                return operator_func(place_name)
            logger.warning(f"[query_local_coordinates] , step.before={step.before}")
            return None

        elif operator_name == 'query_local_routes':
            #  origin, destination, mode
            origin = params.get('origin')
            destination = params.get('destination')
            mode = params.get('mode', 'driving')

            # :
            def resolve_place_name(concept_ref: str) -> Optional[str]:
                if not concept_ref:
                    return None
                #  inputs ( step.before)
                if concept_ref in inputs:
                    data = inputs[concept_ref]
                    if isinstance(data, dict):
                        return data.get('local_db_name') or data.get('name') or data.get('place_name') or data.get('formatted_address')
                    elif isinstance(data, str):
                        return data
                #  intermediate_concepts ()
                if concept_ref in intermediate_concepts:
                    data = intermediate_concepts[concept_ref]
                    if isinstance(data, dict):
                        return data.get('local_db_name') or data.get('name') or data.get('place_name') or data.get('formatted_address')
                    elif isinstance(data, str):
                        return data
                #  plan.types ()
                if hasattr(plan, 'types') and plan.types:
                    #  1:  ID 
                    for entity in plan.types:
                        entity_id = entity.get('id') if isinstance(entity, dict) else getattr(entity, 'id', None)
                        entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)
                        if entity_id == concept_ref and entity_name:
                            logger.debug(f"[resolve_place_name]  plan.types : {concept_ref} -> {entity_name}")
                            return entity_name

                    #  2:  ID  (location_DaNang -> "Da Nang")
                    #  concept_ref  location_X , entity.name  X 
                    import re
                    if concept_ref.startswith('location_'):
                        #  location_ , "DaNang" -> ["Da", "Nang"]  "CentreGermany" -> ["Centre", "Germany"]
                        suffix = concept_ref[9:]  #  "location_"
                        # 
                        words = re.findall(r'[A-Z][a-z]*|[a-z]+', suffix)
                        search_pattern = '.*'.join(words).lower()  # "da.*nang"  "centre.*germany"

                        for entity in plan.types:
                            entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)
                            entity_type = entity.get('concept_type') if isinstance(entity, dict) else getattr(entity, 'concept_type', None)
                            entity_type_str = str(entity_type).lower() if entity_type else ''

                            #  location 
                            if entity_name and 'location' in entity_type_str:
                                if re.search(search_pattern, entity_name.lower()):
                                    logger.info(f"[resolve_place_name]  plan.types : {concept_ref} -> {entity_name}")
                                    return entity_name

                # ,()
                if concept_ref not in ['current_location', 'user_location', 'origin', 'destination']:
                    return concept_ref
                return None

            #  origin  destination
            resolved_origin = resolve_place_name(origin)
            resolved_dest = resolve_place_name(destination)

            #  params , step.before 
            if not resolved_origin or not resolved_dest:
                before_concepts = list(step.before)
                if len(before_concepts) >= 2:
                    if not resolved_origin:
                        resolved_origin = resolve_place_name(before_concepts[0])
                    if not resolved_dest:
                        resolved_dest = resolve_place_name(before_concepts[1])
                elif len(before_concepts) == 1:
                    # ( geocoded_destination),
                    resolved = resolve_place_name(before_concepts[0])
                    if resolved and not resolved_dest:
                        resolved_dest = resolved

            logger.info(f"[query_local_routes] : origin={resolved_origin}, destination={resolved_dest}, mode={mode}")

            #  origin  None(operator  destination )
            if resolved_dest:
                return operator_func(resolved_origin, resolved_dest, mode)
            return None

        elif operator_name == 'query_local_travel_time':
            #  origin, destination, mode
            origin = params.get('origin')
            destination = params.get('destination')
            mode = params.get('mode', 'driving')

            # :
            def resolve_place_name_tt(concept_ref: str) -> Optional[str]:
                if not concept_ref:
                    return None
                #  inputs ( step.before)
                if concept_ref in inputs:
                    data = inputs[concept_ref]
                    if isinstance(data, dict):
                        return data.get('local_db_name') or data.get('name') or data.get('place_name') or data.get('formatted_address')
                    elif isinstance(data, str):
                        return data
                #  intermediate_concepts ()
                if concept_ref in intermediate_concepts:
                    data = intermediate_concepts[concept_ref]
                    if isinstance(data, dict):
                        return data.get('local_db_name') or data.get('name') or data.get('place_name') or data.get('formatted_address')
                    elif isinstance(data, str):
                        return data
                #  plan.types ()
                if hasattr(plan, 'types') and plan.types:
                    #  1:  ID 
                    for entity in plan.types:
                        entity_id = entity.get('id') if isinstance(entity, dict) else getattr(entity, 'id', None)
                        entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)
                        if entity_id == concept_ref and entity_name:
                            logger.debug(f"[resolve_place_name_tt]  plan.types : {concept_ref} -> {entity_name}")
                            return entity_name

                    #  2:  ID  (location_DaNang -> "Da Nang")
                    import re
                    if concept_ref.startswith('location_'):
                        suffix = concept_ref[9:]  #  "location_"
                        words = re.findall(r'[A-Z][a-z]*|[a-z]+', suffix)
                        search_pattern = '.*'.join(words).lower()

                        for entity in plan.types:
                            entity_name = entity.get('name') if isinstance(entity, dict) else getattr(entity, 'name', None)
                            entity_type = entity.get('concept_type') if isinstance(entity, dict) else getattr(entity, 'concept_type', None)
                            entity_type_str = str(entity_type).lower() if entity_type else ''

                            if entity_name and 'location' in entity_type_str:
                                if re.search(search_pattern, entity_name.lower()):
                                    logger.info(f"[resolve_place_name_tt]  plan.types : {concept_ref} -> {entity_name}")
                                    return entity_name

                # ,()
                if concept_ref not in ['current_location', 'user_location', 'origin', 'destination']:
                    return concept_ref
                return None

            #  origin  destination
            resolved_origin = resolve_place_name_tt(origin)
            resolved_dest = resolve_place_name_tt(destination)

            #  params , step.before 
            if not resolved_origin or not resolved_dest:
                before_concepts = list(step.before)
                if len(before_concepts) >= 2:
                    if not resolved_origin:
                        resolved_origin = resolve_place_name_tt(before_concepts[0])
                    if not resolved_dest:
                        resolved_dest = resolve_place_name_tt(before_concepts[1])
                elif len(before_concepts) == 1:
                    # ( geocoded_destination),
                    resolved = resolve_place_name_tt(before_concepts[0])
                    if resolved and not resolved_dest:
                        resolved_dest = resolved

            logger.info(f"[query_local_travel_time] : origin={resolved_origin}, destination={resolved_dest}, mode={mode}")

            if resolved_origin and resolved_dest:
                return operator_func(resolved_origin, resolved_dest, mode)
            return None

        elif operator_name == 'query_local_nearby_places':
            #  center, place_type, radius_meters()
            center = params.get('center') or params.get('reference_place')
            place_type = params.get('place_type') or params.get('category')
            radius_meters = params.get('radius_meters') or params.get('radius')

            if not center:
                for concept_id in step.before:
                    if concept_id in inputs:
                        center = inputs[concept_id].get('name', '')
                        if center:
                            break

            if center and place_type:
                results = operator_func(center, place_type, radius_meters)
                # , Google Maps place_search
                if not results:
                    logger.info(f"[query_local_nearby_places] , place_search API")
                    try:
                        # 
                        from src.agent.operators import geocode as geocode_op
                        center_loc = geocode_op(self.client, center)
                        if center_loc:
                            #  place_search
                            from src.agent.operators import place_search as place_search_op
                            fallback_radius = radius_meters if radius_meters else 1000
                            results = place_search_op(
                                self.client,
                                location=center_loc,
                                radius=fallback_radius,
                                place_type=None,  # 
                                keyword=place_type  #  category 
                            )
                            if results:
                                logger.info(f"[query_local_nearby_places] OK  place_search :  {len(results)} ")

                                #  ,
                                if radius_meters and radius_meters > 0:
                                    import math
                                    center_lat = center_loc.get('lat')
                                    center_lng = center_loc.get('lng')

                                    if center_lat and center_lng:
                                        #  distance_meters 
                                        for place in results:
                                            place_lat = place.get('lat')
                                            place_lng = place.get('lng')
                                            if place_lat and place_lng:
                                                # Haversine 
                                                R = 6371000  # ()
                                                lat1, lat2 = math.radians(center_lat), math.radians(place_lat)
                                                dlat = math.radians(place_lat - center_lat)
                                                dlng = math.radians(place_lng - center_lng)
                                                a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng/2)**2
                                                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                                                distance = R * c
                                                place['distance_meters'] = round(distance, 1)

                                        # 
                                        original_count = len(results)
                                        results = [
                                            p for p in results
                                            if p.get('distance_meters') is not None and p.get('distance_meters') <= radius_meters
                                        ]
                                        logger.info(f"[query_local_nearby_places] : {original_count} -> {len(results)} (radius={radius_meters}m)")
                    except Exception as e:
                        logger.warning(f"[query_local_nearby_places]  place_search : {e}")
                return results if results else []
            return []

        # 
        if operator_name == 'geocode':
            # 
            location_names = []

            # 1:  params 
            if params.get('text'):
                location_names = [params['text']]

            # 2: 
            if not location_names:
                for concept_id in step.before:
                    if concept_id in inputs:
                        name = inputs[concept_id].get('name', '')
                        if name:
                            location_names.append(name)

            #  anchor (location bias)
            anchor = None
            if params.get('anchor'):
                anchor_concept_id = params['anchor']
                if anchor_concept_id in inputs:
                    lat, lng = _extract_coordinates_from_concept(inputs[anchor_concept_id])
                    if lat and lng:
                        anchor = {'lat': lat, 'lng': lng}

            #  geocode
            from .state import Location
            locations = []
            origin_location = None

            for i, name in enumerate(location_names):
                result = operator_func(client, name, anchor=anchor)
                if result:
                    loc = Location(
                        name=name,
                        lat=result['lat'],
                        lng=result['lng'],
                        address=result.get('formatted_address'),
                        place_id=result.get('place_id')
                    )
                    locations.append(loc)
                    if i == 0:
                        origin_location = loc
                else:
                    logger.warning(f"[geocode] : {name}")
                    locations.append(Location(name=name))

            #  locations  origin
            return {'locations': locations, 'origin_location': origin_location}

        elif operator_name == 'place_search':
            #  step.before 
            location = None
            for concept_id in step.before:
                if concept_id in inputs:
                    lat, lng = _extract_coordinates_from_concept(inputs[concept_id])
                    if lat and lng:
                        location = (lat, lng)
                        break

            if not location:
                logger.error(f"[execute_operator] place_search  location")
                return []

            # 
            place_type = params.get('place_type')
            keyword = params.get('keyword')

            #  : 'radius'  'radius_m' 
            radius = params.get('radius') or params.get('radius_m', 5000)

            return operator_func(
                client,
                location,
                radius=radius,
                place_type=place_type,
                keyword=keyword,
                min_rating=params.get('min_rating'),
                open_now=params.get('open_now', False)
            )

        elif operator_name == 'place_details':
            place_id = params.get('place_id')
            if not place_id:
                # 
                for concept_id in step.before:
                    if concept_id in inputs:
                        place_id = inputs[concept_id].get('place_id')
                        if place_id:
                            break
            return operator_func(client, place_id)

        elif operator_name == 'directions':
            origin = params.get('origin')
            destination = params.get('destination')
            mode = params.get('mode', inputs.get('mode', 'driving'))
            waypoints = params.get('waypoints')
            departure_time = params.get('departure_time')

            # ID
            if origin and isinstance(origin, str) and origin in inputs:
                lat, lng = _extract_coordinates_from_concept(inputs[origin])
                if lat and lng:
                    origin = f"{lat},{lng}"

            if destination and isinstance(destination, str) and destination in inputs:
                lat, lng = _extract_coordinates_from_concept(inputs[destination])
                if lat and lng:
                    destination = f"{lat},{lng}"

            logger.info(f"[directions]  API: {origin} -> {destination} (mode={mode}, waypoints={waypoints})")
            # :  directions  waypoints,
            return operator_func(client, origin, destination, mode, departure_time)

        elif operator_name == 'distance_matrix':
            origins = params.get('origins', [])
            destinations = params.get('destinations', [])
            mode = inputs.get('mode', 'driving')
            departure_time = params.get('departure_time')

            return operator_func(client, origins, destinations, mode, departure_time)

        elif operator_name == 'filter_places':
            # 
            places = []
            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, list):
                        places = data
                        break
                    elif isinstance(data, dict) and 'places' in data:
                        places = data['places']
                        break

            return operator_func(
                places,
                min_rating=params.get('min_rating'),
                price_level=params.get('price_level'),
                place_types=params.get('place_types'),
                open_at=params.get('open_at')
            )

        elif operator_name == 'filter_places_by_time':
            # 
            from src.agent.operators import filter_places_by_time as filter_by_time_func

            # 
            places = []
            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, list):
                        places = data
                        break
                    elif isinstance(data, dict) and 'places' in data:
                        places = data['places']
                        break

            day_of_week = params.get('day_of_week')
            target_time = params.get('target_time')

            if not day_of_week or not target_time:
                logger.warning(f"[filter_places_by_time]  day_of_week  target_time ")
                return places

            logger.info(f"[filter_places_by_time]  {day_of_week} {target_time} , {len(places)} ")
            return filter_by_time_func(places, day_of_week, target_time)

        elif operator_name == 'nearest':
            # 
            anchor = None
            candidates = []

            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, dict) and 'lat' in data and 'lng' in data:
                        if anchor is None:
                            anchor = data
                        else:
                            candidates.append(data)
                    elif isinstance(data, list):
                        candidates = data

            if not anchor:
                logger.error(f"[execute_operator] nearest ")
                return None

            return operator_func(anchor, candidates, metric=params.get('metric', 'haversine'))

        elif operator_name == 'within_radius':
            center = None
            candidates = []
            #  : 'radius'  'radius_m' 
            radius_m = params.get('radius') or params.get('radius_m', 5000)

            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, dict) and 'lat' in data:
                        center = data
                    elif isinstance(data, list):
                        candidates = data

            if not center:
                logger.error(f"[execute_operator] within_radius ")
                return []

            return operator_func(center, radius_m, candidates)

        elif operator_name == 'batch_geocode':
            # :
            place_names = []

            #  1:  step.before 
            # LLM  DAG  before 
            for concept_id in step.before:
                if isinstance(concept_id, str):
                    # (ID)
                    if concept_id not in inputs:
                        # ,
                        if concept_id.strip():
                            place_names.append(concept_id)
                    else:
                        # ID, inputs 
                        data = inputs[concept_id]
                        if isinstance(data, list):
                            place_names.extend([item if isinstance(item, str) else str(item) for item in data if item])
                        elif isinstance(data, str):
                            if data.strip():
                                place_names.append(data)
                        elif isinstance(data, dict):
                            # P0: ( name, type, role )
                            # : {"name": "Place A, Place B, Place C", "type": "object", ...}
                            name_str = data.get('name', '')
                            if name_str and isinstance(name_str, str):
                                # 
                                if ',' in name_str or '->' in name_str:
                                    #  "A, B, C"  "A -> B -> C" 
                                    separator = '->' if '->' in name_str else ','
                                    names = [n.strip() for n in name_str.split(separator) if n.strip()]
                                    place_names.extend(names)
                                    logger.info(f"[batch_geocode]  {len(names)} : {names}")
                                else:
                                    # 
                                    place_names.append(name_str.strip())
                            # : 'attributes' 
                            attrs = data.get('attributes', {})
                            if isinstance(attrs, dict) and 'places' in attrs:
                                attr_places = attrs['places']
                                if isinstance(attr_places, list):
                                    place_names.extend([p for p in attr_places if isinstance(p, str)])

            #  2:  params  place_names()
            if not place_names:
                place_names_param = params.get('place_names')
                if isinstance(place_names_param, list):
                    place_names = place_names_param
                elif isinstance(place_names_param, str):
                    if place_names_param in inputs:
                        data = inputs[place_names_param]
                        if isinstance(data, list):
                            place_names = [item if isinstance(item, str) else str(item) for item in data]
                        elif isinstance(data, str):
                            place_names = [data]

            # ()
            anchor = None
            anchor_id = params.get('anchor')
            if anchor_id and anchor_id in inputs:
                lat, lng = _extract_coordinates_from_concept(inputs[anchor_id])
                if lat and lng:
                    anchor = {'lat': lat, 'lng': lng}

            if not place_names:
                logger.warning(f"[batch_geocode] ")
                return []

            logger.info(f"[batch_geocode]  {len(place_names)} : {place_names}")
            return operator_func(client, place_names, anchor=anchor)

        elif operator_name == 'batch_place_details':
            # 
            places = []
            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]

                    #   geocode 
                    if isinstance(data, dict):
                        #  geocode 
                        if 'locations' in data and data['locations']:
                            #  locations  Location 
                            loc = data['locations'][0]
                            #  dict (batch_place_details )
                            places.append({
                                'name': loc.name,
                                'place_id': loc.place_id,
                                'lat': loc.lat,
                                'lng': loc.lng,
                                'address': getattr(loc, 'address', '')
                            })
                        elif 'place_id' in data:
                            # ( place_id)
                            places.append(data)
                        # else: 
                    elif isinstance(data, list):
                        # :
                        for item in data:
                            if isinstance(item, dict) and 'place_id' in item:
                                places.append(item)

            if not places:
                logger.warning(f"[batch_place_details] ")
                return []

            logger.info(f"[batch_place_details]  {len(places)}  batch_place_details")
            return operator_func(client, places)

        elif operator_name == 'steps_analysis':
            # 
            route = None
            for concept_id in step.before:
                if concept_id in inputs:
                    route = inputs[concept_id]
                    break

            #  : after ()
            after_location = params.get('after')
            if after_location:
                logger.info(f"[steps_analysis]  '{after_location}' ")
                return operator_func(route, after=after_location)
            else:
                return operator_func(route)

        elif operator_name == 'haversine':
            # 
            location_a_id = params.get('location_a')
            location_b_id = params.get('location_b')

            #  _resolve_concept_reference 
            location_a_data = _resolve_concept_reference(location_a_id, inputs, intermediate_concepts)
            location_b_data = _resolve_concept_reference(location_b_id, inputs, intermediate_concepts)

            lat1, lng1 = _extract_coordinates_from_concept(location_a_data)
            lat2, lng2 = _extract_coordinates_from_concept(location_b_data)

            # , location_a/b 
            if (lat1 is None or lng1 is None) and location_a_id and isinstance(location_a_id, str):
                logger.info(f"[haversine]  '{location_a_id}' ")
                from src.agent.operators import query_local_coordinates
                coords_a = query_local_coordinates(location_a_id)
                if coords_a:
                    lat1, lng1 = coords_a.get('lat'), coords_a.get('lng')

            if (lat2 is None or lng2 is None) and location_b_id and isinstance(location_b_id, str):
                logger.info(f"[haversine]  '{location_b_id}' ")
                from src.agent.operators import query_local_coordinates
                coords_b = query_local_coordinates(location_b_id)
                if coords_b:
                    lat2, lng2 = coords_b.get('lat'), coords_b.get('lng')

            if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
                logger.error(f"[haversine] : location_a={location_a_id}, location_b={location_b_id}")
                return None

            return operator_func(lat1, lng1, lat2, lng2)

        elif operator_name == 'bearing':
            # 
            origin_id = params.get('origin') or params.get('location_a')
            dest_id = params.get('destination') or params.get('location_b')

            #  _resolve_concept_reference 
            origin_data = _resolve_concept_reference(origin_id, inputs, intermediate_concepts)
            dest_data = _resolve_concept_reference(dest_id, inputs, intermediate_concepts)

            lat1, lng1 = _extract_coordinates_from_concept(origin_data)
            lat2, lng2 = _extract_coordinates_from_concept(dest_data)

            if lat1 is None or lng1 is None or lat2 is None or lng2 is None:
                logger.error(f"[bearing] : origin={origin_id}, destination={dest_id}")
                return None

            return operator_func(lat1, lng1, lat2, lng2)

        elif operator_name == 'bearing_to_direction':
            # 
            #  params  bearing/angle ID
            bearing_id = params.get('bearing') or params.get('angle')

            #  inputs , intermediate_concepts 
            bearing_value = inputs.get(bearing_id) or intermediate_concepts.get(bearing_id)

            if bearing_value is None:
                logger.error(f"[bearing_to_direction] : {bearing_id}")
                return None

            #  4  8 
            #  N/E/S/W (4 ), 4 
            state = inputs.get('state', {})
            options = state.get('options', []) if state else []
            cardinal_directions = {'north', 'east', 'south', 'west', 'n', 'e', 's', 'w'}
            intercardinal_directions = {'northeast', 'northwest', 'southeast', 'southwest', 'ne', 'nw', 'se', 'sw'}

            options_lower = [str(opt).lower().strip() for opt in options]
            has_intercardinal = any(d in opt for opt in options_lower for d in intercardinal_directions)
            has_cardinal = any(d in opt for opt in options_lower for d in cardinal_directions)

            # (,), 4 
            if has_cardinal and not has_intercardinal:
                num_directions = 4
                logger.info(f"[bearing_to_direction]  4 , 4 ")
            else:
                num_directions = 8

            #  bearing_to_direction 
            return operator_func(bearing_value, num_directions)

        elif operator_name == 'compare_routes':
            # 
            #  params 
            metric = params.get('metric', 'duration')
            mode = params.get('mode', 'min')

            #  inputs 
            routes = []
            for concept_id in step.before:
                route_data = inputs.get(concept_id)
                if route_data:
                    routes.append(route_data)

            if not routes:
                logger.warning("[compare_routes] ")
                return 0

            #  compare_routes  ( client )
            return operator_func(routes, metric, mode)

        elif operator_name == 'filter_routes':
            # 
            #  params 
            condition = params.get('condition', 'contains')
            keyword = params.get('keyword', '')

            #  inputs 
            routes = []
            for concept_id in step.before:
                route_data = inputs.get(concept_id)
                if route_data:
                    routes.append(route_data)

            if not routes:
                logger.warning("[filter_routes] ")
                return 0

            #  filter_routes  ( client )
            return operator_func(routes, condition, keyword)

        elif operator_name == 'extract_distance':
            # 
            #  step.before 
            route_data = None
            for concept_id in step.before:
                if concept_id in inputs:
                    route_data = inputs[concept_id]
                    break

            if not route_data:
                logger.warning("[extract_distance] ")
                return 0.0

            #  extract_distance  ( client )
            return operator_func(route_data)

        elif operator_name == 'extract_duration':
            # 
            #  step.before 
            route_data = None
            for concept_id in step.before:
                if concept_id in inputs:
                    route_data = inputs[concept_id]
                    break

            if not route_data:
                logger.warning("[extract_duration] ")
                return 0.0

            #  extract_duration  ( client )
            return operator_func(route_data)

        elif operator_name == 'calculate_finish_time':
            # 
            #  intermediate_concepts (via inputs) 
            start_time = inputs.get('start_time', '09:00')
            duration_to_lake_louise = inputs.get('duration_to_lake_louise', 0.0)
            duration_to_moraine_lake = inputs.get('duration_to_moraine_lake', 0.0)

            #  params 
            lake_louise_duration = params.get('lake_louise_duration', 180)
            moraine_lake_duration = params.get('moraine_lake_duration', 180)

            logger.info(f"[calculate_finish_time] : start={start_time}, "
                       f"travel_durations=[{duration_to_lake_louise}, {duration_to_moraine_lake}], "
                       f"stay_durations=[{lake_louise_duration}, {moraine_lake_duration}]")

            #  calculate_finish_time  ( client )
            return operator_func(
                start_time,
                duration_to_lake_louise,
                duration_to_moraine_lake,
                lake_louise_duration,
                moraine_lake_duration
            )

        elif operator_name == 'calculate_latest_visit_time':
            # ()
            #  step.before 
            departure_time = None
            travel_duration = 0.0

            for concept_id in step.before:
                if concept_id in inputs:
                    value = inputs[concept_id]
                    # ( "9:00 AM")
                    if isinstance(value, str) and (':' in value or 'AM' in value or 'PM' in value):
                        # ( "9:00 AM Sunday" -> "09:00")
                        departure_time = self._parse_time_string(value)
                    elif isinstance(value, (int, float)):
                        travel_duration = float(value)
                    elif concept_id == 'travel_duration' or 'duration' in concept_id:
                        travel_duration = float(value) if isinstance(value, (int, float)) else 0.0

            if not departure_time:
                departure_time = "09:00"  # 

            logger.info(f"[calculate_latest_visit_time] : departure={departure_time}, travel_duration={travel_duration}min")

            # ( client )
            return operator_func(
                departure_time=departure_time,
                travel_duration=travel_duration,
                params=params,
                mode=inputs.get('mode', 'driving')
            )

        elif operator_name == 'add_durations':
            # 
            #  step.before 
            durations = []
            for concept_id in step.before:
                if concept_id in inputs:
                    value = inputs[concept_id]
                    # ,
                    if isinstance(value, (int, float, dict)):
                        durations.append(value)
                    # , durations
                    elif isinstance(value, list):
                        durations.extend(value)

            if not durations:
                logger.warning("[add_durations] ")
                return {"total_seconds": 0, "total_minutes": 0, "total_hours": 0, "formatted": "0min"}

            logger.info(f"[add_durations]  {len(durations)} ")

            #  add_durations  ( client )
            return operator_func(durations)

        elif operator_name == 'count_in_route':
            # 
            #  step.before 
            route_data = None
            for concept_id in step.before:
                if concept_id in inputs:
                    route_data = inputs[concept_id]
                    break

            keyword = params.get('keyword', 'turn')

            if not route_data:
                logger.warning("[count_in_route] ")
                return 0

            #  count_in_route  ( client )
            return operator_func(route_data, keyword)

        elif operator_name == 'pairwise_extremes':
            # 
            # 
            locations = []
            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, list):
                        locations.extend(data)
                    elif isinstance(data, dict) and 'lat' in data:
                        locations.append(data)

            metric = params.get('metric', 'haversine')

            if len(locations) < 2:
                logger.warning(f"[pairwise_extremes] : {len(locations)}")
                return None, None, 0.0

            logger.info(f"[pairwise_extremes]  {len(locations)} ")
            # ( role, time, day )
            return operator_func(locations, metric)

        elif operator_name == 'open_at_time':
            # 
            # 
            place_detail = None
            for concept_id in step.before:
                if concept_id in inputs:
                    data = inputs[concept_id]
                    if isinstance(data, dict) and 'opening_hours' in data:
                        place_detail = data
                        break

            if not place_detail:
                logger.warning("[open_at_time] ")
                return None

            #  params , datetime
            time_str = params.get('time', '17:00')
            day_str = params.get('day', 'Saturday')

            # , local_dt
            local_dt = self._build_datetime_from_params(time_str, day_str)

            logger.info(f"[open_at_time]  {place_detail.get('name', 'unknown')}  {local_dt} ")
            # ( time, day, measure_type )
            return operator_func(place_detail, local_dt)

        elif operator_name == 'tsp_tw':
            # TSP 
            distance_matrix_data = params.get('distance_matrix')
            locations = params.get('locations', [])
            service_times = params.get('service_times')
            time_windows = params.get('time_windows')
            start_time = params.get('start_time')
            time_budget = params.get('time_budget')
            mode = params.get('mode', 'driving')  #  : 

            #  :  (geocoded_origin)
            origin_location = None
            for concept_id in step.before:
                if 'origin' in concept_id.lower() and concept_id in inputs:
                    data = inputs[concept_id]
                    # geocoded_origin  origin_location 
                    if isinstance(data, dict):
                        if 'lat' in data and 'lng' in data:
                            origin_location = data
                            logger.info(f"[tsp_tw]  {concept_id} : {data.get('name', data.get('formatted_address', 'unknown'))}")
                            break
                        elif 'origin_location' in data and data['origin_location']:
                            origin_location = data['origin_location']
                            logger.info(f"[tsp_tw]  {concept_id}.origin_location ")
                            break

            # Resolve string location names produced by the planner into local place records.
            if locations and all(isinstance(loc, str) for loc in locations):
                try:
                    from src.agent.operators import query_local_places_batch
                    resolved_locations = query_local_places_batch(locations)
                    if resolved_locations:
                        locations = resolved_locations
                        logger.info(f"[tsp_tw] resolved {len(locations)} location names through local cache")
                    else:
                        locations = [{'name': loc} for loc in locations]
                except Exception as exc:
                    logger.warning(f"[tsp_tw] failed to resolve string locations: {exc}")
                    locations = [{'name': loc} for loc in locations]

            # P0+: read locations from upstream details/geocoding outputs when params did not include them.
            if not locations:
                for concept_id in step.before:
                    if concept_id in inputs:
                        data = inputs[concept_id]
                        if isinstance(data, list) and data and isinstance(data[0], dict):
                            if 'lat' in data[0] and 'lng' in data[0]:
                                locations = data
                                logger.info(f"[tsp_tw] using {len(locations)} locations from {concept_id}")
                                break

            #  :  locations 
            #  TSP 
            if origin_location and locations:
                #  Location dataclass  dict 
                if hasattr(origin_location, 'lat'):
                    # Location dataclass
                    origin_lat = origin_location.lat
                    origin_lng = origin_location.lng
                    origin_name = getattr(origin_location, 'name', '') or getattr(origin_location, 'address', 'Origin')
                    # 
                    origin_dict = {
                        'name': origin_name,
                        'lat': origin_lat,
                        'lng': origin_lng,
                        'formatted_address': getattr(origin_location, 'address', ''),
                        'place_id': getattr(origin_location, 'place_id', '')
                    }
                else:
                    # 
                    origin_lat = origin_location.get('lat', 0)
                    origin_lng = origin_location.get('lng', 0)
                    origin_name = origin_location.get('name', origin_location.get('formatted_address', 'Origin'))
                    origin_dict = origin_location
                    if 'name' not in origin_dict:
                        origin_dict['name'] = origin_name

                # 
                is_duplicate = any(
                    loc.get('name', '') == origin_name or
                    (abs(loc.get('lat', 0) - origin_lat) < 0.0001 and
                     abs(loc.get('lng', 0) - origin_lng) < 0.0001)
                    for loc in locations
                )
                if not is_duplicate:
                    locations = [origin_dict] + locations
                    logger.info(f"[tsp_tw]  '{origin_name}' , {len(locations)} ")

            # P0:  step.before  service_times (visit_durations)
            if not service_times:
                for concept_id in step.before:
                    if concept_id in inputs:
                        data = inputs[concept_id]
                        # 1:  {"Senso-ji": 1.0, "Shibuya Crossing": 1.5, ...}
                        if isinstance(data, dict) and data:
                            first_val = next(iter(data.values()), None)
                            if isinstance(first_val, (int, float)):
                                service_times = data
                                logger.info(f"[tsp_tw]  {concept_id} : {service_times}")
                                break
                        # 2:  [1.0, 1.5, 2.0, 1.5]
                        elif isinstance(data, list) and data and isinstance(data[0], (int, float)):
                            service_times = data
                            logger.info(f"[tsp_tw]  {concept_id} : {service_times}")
                            break

            # P0: ()
            if not service_times and locations:
                state = inputs.get('state', {})
                question = state.get('question', '')
                if question:
                    service_times = self._extract_visit_durations_from_question(question, locations)
                    if service_times:
                        logger.info(f"[tsp_tw] : {service_times}")

            # P0:  service_times ( locations )
            if service_times and isinstance(service_times, dict) and locations:
                location_names = [loc.get('name', '') for loc in locations]
                service_times_list = []
                for idx, name in enumerate(location_names):
                    #  :  (idx=0)  0
                    if idx == 0:
                        # , 0
                        service_times_list.append(0.0)
                        logger.info(f"[tsp_tw]  '{name}'  0")
                        continue

                    # 
                    duration = service_times.get(name)
                    if duration is None:
                        # 
                        for key, val in service_times.items():
                            if key.lower() in name.lower() or name.lower() in key.lower():
                                duration = val
                                break
                    service_times_list.append(duration if duration is not None else 1.0)  #  1 
                service_times = service_times_list
                logger.info(f"[tsp_tw] : {service_times}")

            # P0:  step.before  time_budget
            if not time_budget:
                for concept_id in step.before:
                    if concept_id in inputs:
                        data = inputs[concept_id]
                        if isinstance(data, (int, float)) and 0 < data < 48:  # 
                            time_budget = data
                            logger.info(f"[tsp_tw]  {concept_id} : {time_budget} ")
                            break

            # P0:  time_budget ( -> )
            if time_budget and time_budget > 24:
                logger.warning(f"[tsp_tw] time_budget={time_budget} ,")
                time_budget = time_budget / 60

            # :  step.before 
            if not distance_matrix_data:
                for concept_id in step.before:
                    if concept_id in inputs and concept_id == 'distance_matrix':
                        distance_matrix_data = inputs[concept_id]
                        break

            return operator_func(
                distance_matrix_data,
                locations,
                service_times,
                time_windows,
                start_time,
                time_budget,
                mode  #  : 
            )

        else:
            # : 
            logger.warning(f"[execute_operator]  {operator_name} ")
            return operator_func(client, **params)

    def _store_outputs(
        self,
        step: TransformationStep,
        outputs: Any,
        intermediate_concepts: Dict[str, Any]
    ):
        """
        

        Args:
            step: 
            outputs: 
            intermediate_concepts: 
        """
        if len(step.after) == 1:
            # 
            concept_id = step.after[0]
            intermediate_concepts[concept_id] = outputs
        else:
            # ( outputs )
            if isinstance(outputs, (list, tuple)) and len(outputs) == len(step.after):
                for concept_id, output_data in zip(step.after, outputs):
                    intermediate_concepts[concept_id] = output_data
            else:
                # ,
                for concept_id in step.after:
                    intermediate_concepts[concept_id] = outputs

    def _summarize_output(self, outputs: Any) -> str:
        """()"""
        if outputs is None:
            return "None"
        elif isinstance(outputs, list):
            return f"List[{len(outputs)} items]"
        elif isinstance(outputs, dict):
            keys = list(outputs.keys())[:3]
            return f"Dict({', '.join(keys)}{'...' if len(outputs) > 3 else ''})"
        else:
            return str(type(outputs).__name__)

