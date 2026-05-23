from typing import TypedDict, List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from typing_extensions import NotRequired, Required


class CoreConcept(str, Enum):
    """ ( Xu et al., 2023)"""
    LOCATION = "location"  # 
    FIELD = "field"  # 
    OBJECT = "object"  # 
    EVENT = "event"  # 
    NETWORK = "network"  # 
    AMOUNT = "amount"  # 
    PROPORTION = "proportion"  # 


class FunctionalRole(str, Enum):
    """ ( Xu et al., 2023)"""
    MEASURE = "measure"  # 
    CONDITION = "condition"  # 
    SUB_CONDITION = "sub_condition"  # 
    SUPPORT = "support"  # 
    EXTENT = "extent"  # 
    TEMPORAL_EXTENT = "temporal_extent"  # 


@dataclass
class Location:
    """"""

    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    place_id: Optional[str] = None


@dataclass
class ConceptEntity:
    """:"""
    name: str
    concept_type: Optional[CoreConcept] = None
    functional_role: Optional[FunctionalRole] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedInfo:
    """"""

    locations: List[str]
    start_location: Optional[str] = None
    transportation_mode: str = "driving"
    time_constraints: Dict[str, Any] = None
    visit_durations: Dict[str, float] = None
    total_time_available: Optional[float] = None
    start_time: Optional[str] = None
    preferences: Dict[str, Any] = None
    # : 
    concept_entities: List[ConceptEntity] = field(default_factory=list)


@dataclass
class TransformationStep:
    """"""
    before: List[str]  # ID
    after: List[str]  # ID
    operator: str  # 
    description: Optional[str] = None  # 
    params: Dict[str, Any] = field(default_factory=dict)  # 


@dataclass
class TransformationPlan:
    """
     -  ideas.txt  Transformation JSON 

     Planner ,
    """
    types: List[ConceptEntity]  # (ID)
    extent: List[str]  #  ( ["Dubai Mall"])
    temporal: List[str]  #  ( ["Tue 09:15"])
    transformations: List[TransformationStep]  # 
    measure: str  #  (nearest, route, count, order, distance, bearing, ...)
    mode: str = "driving"  #  (driving, walking, transit, bicycling)
    params: Dict[str, Any] = field(default_factory=dict)  #  (radius_m, min_rating, price_level, ...)


class SpatialAgentState(TypedDict, total=False):
    """LangGraph"""

    # 
    question: Required[str]
    options: NotRequired[List[str]]
    correct_answer: NotRequired[Optional[int]]
    question_id: NotRequired[Optional[int]]  # : context cache

    # 
    parsed_info: NotRequired[Optional[ParsedInfo]]
    intent: NotRequired[Optional[str]]  # nearby, routing, trip, poi

    # 
    locations: NotRequired[List[Location]]
    origin_location: NotRequired[Optional[Location]]

    # API
    api_results: NotRequired[Dict[str, Any]]

    # 
    calculations: NotRequired[Dict[str, Any]]

    # 
    predicted_option: NotRequired[Optional[int]]
    evaluation: NotRequired[Dict[str, Any]]

    # 
    final_answer: NotRequired[Optional[str]]

    # 
    error: NotRequired[Optional[str]]

    # 
    debug_info: NotRequired[Dict[str, Any]]

    # : 
    concept_flow: NotRequired[List[Dict[str, Any]]]  # 

    # : ( plan)
    transformation_plan: NotRequired[Optional[TransformationPlan]]

    # : (key=ID, value=)
    intermediate_concepts: NotRequired[Dict[str, Any]]
