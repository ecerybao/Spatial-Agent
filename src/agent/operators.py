"""
 - 

 31 , 5 :

## 0.  (6  - Phase 2 )
- query_local_place: ( geocode)
- query_local_coordinates: ( haversine )
- query_local_routes: ( directions)
- query_local_travel_time: ( distance_matrix)
- query_local_places_batch: ()
- query_local_nearby_places: ( place_search)

## 1.  API  (12 )
- geocode: (/->), anchor 
- batch_geocode: ,
- reverse_geocode: (->)
- place_search: ,///
- place_details: (,,)
- batch_place_details: 
- directions: ( driving/walking/transit/bicycling)
- distance_matrix: 
- timezone: 
- haversine:  Haversine ()
- bearing: (0-360 degrees ,0=)
- bearing_to_direction: (N/NE/E/SE/S/SW/W/NW)

## 2.  (8 )
- open_at_time: ()
- filter_places: ///
- nearest: ( haversine/travel_time )
- within_radius: 
- steps_analysis: (,,)
- pairwise_extremes: 
- tsp_tw: ( OR-Tools)
- service_area: /()

## 3. Routing  (4 )
- compare_routes: ,(/)
- filter_routes: ( "stairs", "toll", "roundabout")
- extract_distance: ()
- extract_duration: ()

## 4. Trip  (1 )
- calculate_finish_time: ()

##  (2 )
- _extract_metric_value:  Google Maps API 
- _get_lat_lng:  Location 
"""

import json
import logging
import re
from datetime import datetime, time as dt_time
from typing import Any, Dict, List, Optional, Tuple

from ..tools.google_maps import GoogleMapsClient
from ..utils.optimization import TripOptimizer, haversine, bearing, bearing_to_direction
from ..utils.logging_utils import log_highlight_event

logger = logging.getLogger("spatial_agent.operators")


def _extract_metric_value(data: Any, default: float = 0.0) -> float:
    """
     Google Maps API 

    :
    1. : {'value': 123, 'text': '123 m'}
    2. : 123

    Args:
        data: API 
        default: ()

    Returns:
        
    """
    if isinstance(data, dict):
        return data.get('value', default)
    elif isinstance(data, (int, float)):
        return data
    else:
        return default


def _get_lat_lng(location: Any) -> Tuple[Optional[float], Optional[float]]:
    """
     Location 

    :
    1. Location : hasattr(location, 'lat')
    2. : location.get('lat')

    Args:
        location: Location 

    Returns:
        (lat, lng) , (None, None)
    """
    if hasattr(location, 'lat') and hasattr(location, 'lng'):
        return location.lat, location.lng
    elif isinstance(location, dict):
        return location.get('lat'), location.get('lng')
    else:
        return None, None


def _infer_region_from_context(question: str = "", anchor_address: str = None) -> Optional[str]:
    """
    

    Args:
        question: 
        anchor_address:  formatted_address

    Returns:
        (ISO 3166-1 alpha-2), 'bd', 'ae', 'uk', 'us'
    """
    #  1: ()
    if anchor_address:
        # 
        country_mappings = {
            'Bangladesh': 'bd',
            'United Arab Emirates': 'ae',
            'UAE': 'ae',
            'United Kingdom': 'uk',
            'UK': 'uk',
            'United States': 'us',
            'USA': 'us',
            'Canada': 'ca',
            'India': 'in',
            'Egypt': 'eg',
            'Germany': 'de',
            'France': 'fr',
            'Japan': 'jp',
            'China': 'cn',
            'Singapore': 'sg',
            'Malaysia': 'my',
            'Indonesia': 'id',
            'Thailand': 'th',
            'South Korea': 'kr',
            'Australia': 'au',
            'New Zealand': 'nz',
            'South Africa': 'za',
            'Brazil': 'br',
            'Mexico': 'mx',
            'Argentina': 'ar',
            'Colombia': 'co',
            'Peru': 'pe',
            'Italy': 'it',
            'Spain': 'es',
            'Netherlands': 'nl',
            'Belgium': 'be',
            'Switzerland': 'ch',
            'Austria': 'at',
            'Poland': 'pl',
            'Turkey': 'tr',
            'Saudi Arabia': 'sa',
            'Israel': 'il',
            'Pakistan': 'pk',
            'Vietnam': 'vn',
            'Philippines': 'ph',
        }

        for country, code in country_mappings.items():
            if country in anchor_address:
                logger.debug(f"[region] : {country} -> {code}")
                return code

    #  2: 
    if question:
        text_lower = question.lower()

        # /
        location_hints = {
            # 
            'bangladesh': 'bd', 'dhaka': 'bd', 'rangamati': 'bd', 'sylhet': 'bd', 'habiganj': 'bd',
            # 
            'dubai': 'ae', 'abu dhabi': 'ae', 'uae': 'ae', 'emirates': 'ae',
            # 
            'london': 'uk', 'british': 'uk', 'england': 'uk', 'scotland': 'uk',
            # 
            'new york': 'us', 'los angeles': 'us', 'chicago': 'us', 'boston': 'us',
            'san francisco': 'us', 'seattle': 'us', 'miami': 'us',
            # 
            'toronto': 'ca', 'vancouver': 'ca', 'montreal': 'ca', 'ottawa': 'ca',
            # 
            'tokyo': 'jp', 'osaka': 'jp', 'kyoto': 'jp',
            # 
            'paris': 'fr', 'marseille': 'fr', 'lyon': 'fr',
            # 
            'berlin': 'de', 'munich': 'de', 'hamburg': 'de',
            # 
            'singapore': 'sg',
            # 
            'mumbai': 'in', 'delhi': 'in', 'bangalore': 'in', 'kolkata': 'in',
            # 
            'beijing': 'cn', 'shanghai': 'cn', 'guangzhou': 'cn', 'shenzhen': 'cn',
            # 
            'sydney': 'au', 'melbourne': 'au', 'brisbane': 'au',
            # 
            'rome': 'it', 'madrid': 'es', 'amsterdam': 'nl', 'cairo': 'eg',
        }

        for hint, code in location_hints.items():
            if hint in text_lower:
                logger.debug(f"[region] : '{hint}' -> {code}")
                return code

    #  3:  None( API )
    return None


# ============================================================================
#  (Phase 2: )
# ============================================================================

def query_local_place(place_name: str) -> Optional[Dict[str, Any]]:
    """
    (), geocode

    Args:
        place_name: 

    Returns:
        {place_name, information}  None
        information : "- Location: xxx\n- Open: xxx\n- Rating: xxx"

    Note:
         intent  trip  routing 
    """
    logger.info(f"[query_local_place] : {place_name}")

    try:
        from src.tools.local_context_db import ContextManager

        # 
        if not ContextManager.should_use_local_db():
            logger.debug(f"[query_local_place]  intent ")
            return None

        db = ContextManager.get_db()

        if db and db.is_connected():
            # 
            variations = [place_name]

            # ( "Brassica, Bexley"),
            if ',' in place_name:
                variations.append(place_name.split(',')[0].strip())

            #  "in"( "Museum in Sydney"),
            #  variations 

            for variant in variations:
                place_info = db.get_place_by_name(variant, fuzzy=True)
                if place_info:
                    logger.info(f"[query_local_place] OK : {place_info.get('place_name')} (: {variant})")
                    return {
                        'place_name': place_info.get('place_name'),
                        'information': place_info.get('information', ''),
                        'from_local_db': True
                    }

    except Exception as e:
        logger.warning(f"[query_local_place] : {e}")

    logger.info(f"[query_local_place] , geocode API")
    return None


def query_local_coordinates(place_name: str) -> Optional[Dict[str, Any]]:
    """
    ( haversine ), geocode API

    Args:
        place_name: 

    Returns:
        {"lat": 51.5081, "lng": -0.0759, "from_local_db": True/False}  None
    """
    logger.info(f"[query_local_coordinates] : {place_name}")

    try:
        from src.tools.local_context_db import ContextManager

        db = ContextManager.get_db()

        if db and db.is_connected():
            coords = db.get_place_coordinates(place_name, fuzzy=True)
            if coords:
                lat, lng = coords
                logger.info(f"[query_local_coordinates] OK : ({lat}, {lng})")
                return {
                    "lat": lat,
                    "lng": lng,
                    "formatted_address": place_name,
                    "from_local_db": True
                }

    except Exception as e:
        logger.warning(f"[query_local_coordinates] : {e}")

    #  geocode API
    logger.info(f"[query_local_coordinates] , geocode API")
    try:
        from src.tools.google_maps import GoogleMapsClient
        client = GoogleMapsClient()
        result = client.geocode(place_name)
        if result:
            logger.info(f"[query_local_coordinates] OK Geocode API : ({result.get('lat')}, {result.get('lng')})")
            return {
                "lat": result.get("lat"),
                "lng": result.get("lng"),
                "formatted_address": result.get("formatted_address", place_name),
                "from_local_db": False
            }
    except Exception as e:
        logger.warning(f"[query_local_coordinates] Geocode API : {e}")

    logger.error(f"[query_local_coordinates] : {place_name}")
    return None


def _parse_routes_with_distances(summary: str) -> List[Dict[str, Any]]:
    """
     summary,

    Args:
        summary:  summary 
            : "1. Via A4 and A14 - (1 min | 0.3 km) ... 2. Via A14 - (1 min | 0.5 km) ..."

    Returns:
        [{
            "name": "Via A4 and A14",
            "total_distance_km": 52.0,
            "total_time_mins": 45
        }, ...]
    """
    import re

    routes = []

    #  -  "1. Via ...", "2. Via ..." 
    route_pattern = r'(\d+)\.\s*(Via\s+[^-]+)\s*-'
    route_matches = list(re.finditer(route_pattern, summary))

    for i, match in enumerate(route_matches):
        route_num = match.group(1)
        route_name = match.group(2).strip()

        # 
        start_pos = match.end()
        if i + 1 < len(route_matches):
            end_pos = route_matches[i + 1].start()
        else:
            end_pos = len(summary)

        route_text = summary[start_pos:end_pos]

        #  - : (X min | Y km)  (X min | Y m)
        distances_km = re.findall(r'\|\s*([0-9.]+)\s*km\)', route_text)
        distances_m = re.findall(r'\|\s*([0-9.]+)\s*m\)', route_text)

        # 
        total_km = sum(float(d) for d in distances_km)
        total_m = sum(float(m) for m in distances_m)
        total_distance = total_km + total_m / 1000

        #  - : (X min | ...)  (X mins | ...)
        times = re.findall(r'\((\d+)\s*mins?\s*\|', route_text)
        total_mins = sum(int(t) for t in times)

        routes.append({
            "route_number": int(route_num),
            "name": route_name,
            "total_distance_km": round(total_distance, 3),
            "total_time_mins": total_mins
        })

        logger.debug(f"[_parse_routes_with_distances] Route {route_num}: {route_name} = {total_distance:.3f} km, {total_mins} mins")

    return routes


def query_local_routes(
    origin: str,
    destination: str,
    mode: str = "driving"
) -> Optional[Dict[str, Any]]:
    """
    (), directions

    Args:
        origin: ( None, destination )
        destination: 
        mode:  (driving/walking/transit/bicycling)

    Returns:
         {legs, summary, all_routes}  None

    Note:
         intent  trip  routing 
    """
    logger.info(f"[query_local_routes] : {origin} -> {destination} ({mode})")

    try:
        from src.tools.local_context_db import ContextManager

        # 
        if not ContextManager.should_use_local_db():
            logger.debug(f"[query_local_routes]  intent ")
            return None

        db = ContextManager.get_db()

        if db and db.is_connected():
            #  mode
            mode_map = {
                "driving": "driving",
                "walking": "walking",
                "transit": "transit",
                "bicycling": "bicycling",
                "car": "driving",
                "foot": "walking"
            }
            normalized_mode = mode_map.get(mode.lower(), mode)

            routes_data = None

            #  1:  origin,
            if origin:
                routes_data = db.get_routes(origin, destination, normalized_mode)

            #  2:  origin , destination ()
            if not routes_data and destination:
                logger.info(f"[query_local_routes] origin , destination ")
                #  destination 
                import sqlite3
                cursor = db._conn.cursor()

                #  destination ( "Brassica in Bexley" vs "Brassica, Bexley")
                dest_variations = [destination]
                if ',' in destination:
                    dest_variations.append(destination.split(',')[0].strip())

                for dest_var in dest_variations:
                    cursor.execute(
                        "SELECT origin, destination, mode, summary FROM routes WHERE destination LIKE ? AND mode = ?",
                        (f'%{dest_var}%', normalized_mode)
                    )
                    rows = cursor.fetchall()
                    if rows:
                        # 
                        row = rows[0]
                        logger.info(f"[query_local_routes]  destination : {row[0]} -> {row[1]}")
                        routes_data = {'summary': row[3]}
                        break

            if routes_data:
                logger.info(f"[query_local_routes] OK ")
                summary = routes_data.get('summary', '')

                #  summary 
                # summary : "1. Via I-70 E - (1 min | 0.3 km) ... 2. Via A14 - (1 min | 0.5 km) ..."
                routes_info = _parse_routes_with_distances(summary)

                return {
                    'legs': [{
                        'summary': summary,
                        'steps': [],  # 
                    }],
                    'waypoints_verified': True,
                    'summary': summary,
                    'routes_info': routes_info,  # 
                    'from_local_db': True
                }

    except Exception as e:
        logger.warning(f"[query_local_routes] : {e}")

    logger.info(f"[query_local_routes] , directions API")
    return None


def query_local_travel_time(
    origin: str,
    destination: str,
    mode: str = "driving"
) -> Optional[Dict[str, Any]]:
    """
    (), distance_matrix

    Args:
        origin: 
        destination: 
        mode: 

    Returns:
         {distance, duration}  None

    Note:
         intent  trip  routing 
    """
    logger.info(f"[query_local_travel_time] : {origin} -> {destination} ({mode})")

    try:
        from src.tools.local_context_db import ContextManager

        # 
        if not ContextManager.should_use_local_db():
            logger.debug(f"[query_local_travel_time]  intent ")
            return None

        db = ContextManager.get_db()

        if db and db.is_connected():
            #  mode
            mode_map = {
                "driving": "driving",
                "walking": "walking",
                "transit": "transit",
                "bicycling": "bicycling",
                "car": "driving",
                "foot": "walking"
            }
            normalized_mode = mode_map.get(mode.lower(), mode)

            # (, question_id)
            travel_time = db.get_travel_time(origin, destination, normalized_mode)

            if travel_time:
                # duration_distance : "Travel Time from A to B by car is 14 mins (3.0 km)."
                duration_distance = travel_time.get('duration_distance', '')
                logger.info(f"[query_local_travel_time] OK : {duration_distance}")

                #  Google Maps API 
                return {
                    'duration_distance': duration_distance,
                    'status': 'OK',
                    'from_local_db': True
                }

    except Exception as e:
        logger.warning(f"[query_local_travel_time] : {e}")

    logger.info(f"[query_local_travel_time] , distance_matrix API")
    return None


def query_local_places_batch(place_names: List[str], fallback_to_api: bool = True) -> List[Dict[str, Any]]:
    """
    , Geocoding API

    Args:
        place_names: 
        fallback_to_api:  Geocoding API( True)

    Returns:
        (,)
    """
    logger.info(f"[query_local_places_batch]  {len(place_names)} ")

    results = []
    missed_names = []  # 
    missed_indices = []  # 

    try:
        from src.tools.local_context_db import ContextManager
        db = ContextManager.get_db()

        for idx, place_name in enumerate(place_names):
            if not place_name or not isinstance(place_name, str):
                logger.warning(f"[query_local_places_batch] : {place_name}")
                results.append(None)
                continue

            place_info = None
            if db:
                place_info = db.get_place_by_name(place_name.strip(), fuzzy=True)

            if place_info and place_info.get('lat') is not None and place_info.get('lng') is not None:
                results.append({
                    'lat': place_info['lat'],
                    'lng': place_info['lng'],
                    'formatted_address': place_info.get('address', ''),
                    'place_id': f"local_{place_info['place_id']}",
                    'name': place_info['place_name'],
                    'rating': place_info.get('rating'),
                    'user_ratings_total': place_info.get('user_ratings_total'),
                    'opening_hours': place_info.get('opening_hours'),
                    'price_level': place_info.get('price_level'),
                    'phone_number': place_info.get('phone_number'),
                    'from_local_db': True
                })
                logger.info(f"  OK {place_name} -> ")
            else:
                results.append(None)  # 
                missed_names.append(place_name)
                missed_indices.append(idx)
                logger.info(f"  X {place_name} -> ")

    except Exception as e:
        logger.warning(f"[query_local_places_batch] : {e}")
        # 
        missed_names = place_names
        missed_indices = list(range(len(place_names)))
        results = [None] * len(place_names)

    hit_count = len(place_names) - len(missed_names)
    logger.info(f"[query_local_places_batch] : {hit_count}/{len(place_names)}")

    # , Geocoding API
    if missed_names and fallback_to_api:
        logger.info(f"[query_local_places_batch]  Geocoding API  {len(missed_names)} ")
        try:
            #  GoogleMapsClient 
            client = GoogleMapsClient()
            api_results = batch_geocode(client, missed_names)
            for i, api_result in enumerate(api_results):
                if api_result:
                    api_result['from_local_db'] = False
                    results[missed_indices[i]] = api_result
                    logger.info(f"  OK {missed_names[i]} -> API ")
                else:
                    logger.warning(f"  X {missed_names[i]} -> API ")
        except Exception as e:
            logger.error(f"[query_local_places_batch] API : {e}")

    #  None ()
    valid_results = [r for r in results if r is not None]
    logger.info(f"[query_local_places_batch] : {len(valid_results)}/{len(place_names)}")

    return valid_results


def query_local_nearby_places(
    center: str,
    place_type: str = None,
    radius_meters: int = None
) -> List[Dict[str, Any]]:
    """
    (), place_search

    Args:
        center:  (reference_place)
        place_type: /( "Restaurants", "Parks")
        radius_meters: (),

    Returns:
          
    """
    logger.info(f"[query_local_nearby_places] : center={center}, type={place_type}, radius={radius_meters}m")

    try:
        from src.tools.local_context_db import ContextManager
        db = ContextManager.get_db()

        if db:
            #  API: get_nearby_places(reference_place, category)
            nearby_places = db.get_nearby_places(center, place_type)

            if nearby_places:
                # ,
                if radius_meters is not None and radius_meters > 0:
                    original_count = len(nearby_places)
                    nearby_places = [
                        p for p in nearby_places
                        if p.get('distance_meters') is not None and p.get('distance_meters') <= radius_meters
                    ]
                    logger.info(f"[query_local_nearby_places] : {original_count} -> {len(nearby_places)} (radius={radius_meters}m)")

                logger.info(f"[query_local_nearby_places] OK :  {len(nearby_places)} ")

                #  Google Maps API 
                results = []
                for place in nearby_places:
                    # :, address/vicinity 
                    #  filter_places_by_time 
                    address = place.get('address') or ''
                    opening_hours = place.get('opening_hours')
                    if opening_hours:
                        # , filter_places_by_time
                        address_with_hours = f"{address}\n- Open: {opening_hours}" if address else f"- Open: {opening_hours}"
                    else:
                        address_with_hours = address

                    results.append({
                        'name': place.get('name'),
                        'rank': place.get('rank'),
                        'lat': place.get('lat'),
                        'lng': place.get('lng'),
                        'address': address_with_hours,
                        'rating': place.get('rating'),
                        'user_ratings_total': place.get('rating_count'),
                        'vicinity': address_with_hours,
                        'distance_meters': place.get('distance_meters'),
                        'opening_hours': opening_hours,  # 
                        'from_local_db': True
                    })

                return results

    except Exception as e:
        logger.warning(f"[query_local_nearby_places] : {e}")

    logger.info(f"[query_local_nearby_places] , place_search API")
    return []


# ============================================================================
#  API 
# ============================================================================

def geocode(
    client: GoogleMapsClient,
    text: str,
    anchor: Optional[Dict[str, Any]] = None,
    region: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    : /

    Args:
        client: Google Maps API 
        text: 
        anchor: (),:,anchor
        region: (), 'bd', 'ae', 'uk'

    Returns:
        {lat, lng, formatted_address, place_id}  None

    Note:
         trip/routing intent, information.
        , information .
         Google Maps API .
    """
    #  information( trip/routing intent)
    local_db_info = None
    try:
        from src.tools.local_context_db import ContextManager
        if ContextManager.should_use_local_db():
            db = ContextManager.get_db()
            if db and db.is_connected():
                place_info = db.get_place_by_name(text, fuzzy=True)
                if place_info:
                    local_db_info = {
                        'name': place_info.get('place_name', text),
                        'information': place_info.get('information', '')
                    }
                    logger.info(f"[LOCAL_DB] geocode : '{text}' -> '{local_db_info['name']}'")
    except Exception as e:
        logger.debug(f"[LOCAL_DB] geocode : {e}")

    logger.info(f"[geocode] : {text}, anchor={bool(anchor)}, region={region}")

    #  region, anchor 
    if not region and anchor:
        anchor_address = anchor.get('formatted_address')
        if anchor_address:
            region = _infer_region_from_context("", anchor_address)

    #  anchor, location_bias
    location_bias = None
    if anchor:
        anchor_lat = anchor.get('lat')
        anchor_lng = anchor.get('lng')
        if anchor_lat is not None and anchor_lng is not None:
            location_bias = (anchor_lat, anchor_lng)
            logger.info(f"[geocode] : ({anchor_lat:.2f}, {anchor_lng:.2f})")

    #  Google Maps API with location bias and region
    result = client.geocode(text, location_bias=location_bias, region=region)

    # : geocoding  anchor, nearby_search
    if not result and location_bias:
        log_highlight_event(
            logger,
            event_type='warning',
            title='Geocoding Fallback Triggered',
            details=[
                f"Query: '{text}'",
                f"Anchor: ({location_bias[0]:.4f}, {location_bias[1]:.4f})",
                f"Region: {region or 'None'}",
                "Attempting progressive nearby_search (10km -> 50km -> 100km)"
            ]
        )

        # : 10km -> 50km -> 100km
        for radius in [10000, 50000, 100000]:
            try:
                logger.info(f"[geocode]  nearby_search (radius={radius/1000:.0f}km)")

                places = client.nearby_search(
                    location=location_bias,
                    radius=radius,
                    keyword=text
                )

                if places:
                    # (/)
                    place = places[0]
                    result = {
                        'lat': place['lat'],
                        'lng': place['lng'],
                        'formatted_address': place.get('vicinity', ''),
                        'place_id': place['place_id']
                    }

                    log_highlight_event(
                        logger,
                        event_type='success',
                        title=f'Fallback Succeeded (radius={radius/1000:.0f}km)',
                        details=[
                            f"Found: {place['name']}",
                            f"Rating: {place.get('rating', 'N/A')}",
                            f"Location: ({place['lat']:.4f}, {place['lng']:.4f})"
                        ]
                    )
                    break  # ,

            except Exception as e:
                logger.debug(f"nearby_search (radius={radius/1000:.0f}km) failed: {e}")
                continue  # 

        # ,
        if not result:
            log_highlight_event(
                logger,
                event_type='error',
                title='All Fallback Attempts Failed',
                details=[
                    f"Query '{text}' could not be resolved",
                    "Tried radii: 10km, 50km, 100km"
                ]
            )

    if result:
        # ,
        if local_db_info:
            result['information'] = local_db_info['information']
            result['from_local_db'] = True
            result['local_db_name'] = local_db_info['name']
            logger.info(f"[geocode] : {result['formatted_address']} ({result['lat']:.4f}, {result['lng']:.4f}) + LOCAL_DB info")
        else:
            logger.info(f"[geocode] : {result['formatted_address']} ({result['lat']:.4f}, {result['lng']:.4f})")
    else:
        logger.warning(f"[geocode] : {text}")

    return result


def reverse_geocode(client: GoogleMapsClient, lat: float, lng: float) -> Optional[str]:
    """
    : 

    Args:
        client: Google Maps API 
        lat: 
        lng: 

    Returns:
          None
    """
    logger.info(f"[reverse_geocode] : ({lat}, {lng})")
    result = client.reverse_geocode(lat, lng)
    logger.info(f"[reverse_geocode] : {result}")
    return result


def place_search(
    client: GoogleMapsClient,
    location: Tuple[float, float],
    radius: int = 5000,
    place_type: Optional[str] = None,
    keyword: Optional[str] = None,
    min_rating: Optional[float] = None,
    open_now: bool = False
) -> List[Dict[str, Any]]:
    """
    : 

    Args:
        client: Google Maps API 
        location: (lat, lng) 
        radius: ()
        place_type: ( 'restaurant', 'hospital')
        keyword: 
        min_rating: 
        open_now: 

    Returns:
         [{name, place_id, lat, lng, rating, types, ...}]
    """
    logger.info(f"[place_search] : {location}, : {radius}m, : {place_type}, : {keyword}")
    logger.info(f"[place_search] : location={location}, radius={radius}, type={place_type}, keyword={keyword}, min_rating={min_rating}, open_now={open_now}")

    results = client.nearby_search(
        location=location,
        radius=radius,
        place_type=place_type,
        keyword=keyword,
        min_rating=min_rating,
        open_now=open_now
    )

    logger.info(f"[place_search]  {len(results)} ")

    # 5
    if results:
        logger.info(f"[place_search] 5:")
        for i, place in enumerate(results[:5]):
            logger.info(f"  {i+1}. {place.get('name')} (: {place.get('rating', 'N/A')}, : {place.get('vicinity', 'N/A')})")

    return results


def place_details(client: GoogleMapsClient, place_id: str) -> Optional[Dict[str, Any]]:
    """
    

    Args:
        client: Google Maps API 
        place_id: ID

    Returns:
         {name, lat, lng, rating, opening_hours, price_level, ...}  None
    """
    # ( local_  place_id, intent  trip/routing)
    try:
        from src.tools.local_context_db import ContextManager
        if ContextManager.should_use_local_db() and place_id.startswith('local_'):
            db = ContextManager.get_db()
            if db and db.is_connected():
                #  place_id,
                place_name = place_id.replace('local_', '')
                place_info = db.get_place_by_name(place_name, fuzzy=True)
                if place_info:
                    logger.info(f"[LOCAL_DB] : {place_name}")
                    return {
                        'place_name': place_info.get('place_name'),
                        'information': place_info.get('information', ''),
                        'place_id': place_id,
                        'from_local_db': True
                    }
    except Exception as e:
        logger.debug(f"[LOCAL_DB] : {e}")

    logger.info(f"[place_details] : place_id={place_id}")
    result = client.get_place_details(place_id)
    if result:
        logger.info(f"[place_details] : {result.get('name')}")
    else:
        logger.warning(f"[place_details] : place_id={place_id}")
    return result


def batch_geocode(
    client: GoogleMapsClient,
    place_names: List[str],
    anchor: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
     - 

    Args:
        client: Google Maps API 
        place_names: 
        anchor: (),

    Returns:
        , {lat, lng, formatted_address, place_id}
    """
    logger.info(f"[batch_geocode] : {len(place_names)} ")

    results = []
    for place_name in place_names:
        if not place_name or not isinstance(place_name, str):
            logger.warning(f"[batch_geocode] : {place_name}")
            continue

        geocoded = geocode(client, place_name.strip(), anchor=anchor)
        if geocoded:
            results.append(geocoded)
            # 
            if geocoded.get('lat') is not None:
                if geocoded.get('from_local_db'):
                    logger.info(f"  OK {place_name} -> ({geocoded['lat']:.4f}, {geocoded['lng']:.4f}) + LOCAL_DB")
                else:
                    logger.info(f"  OK {place_name} -> ({geocoded['lat']:.4f}, {geocoded['lng']:.4f})")
            else:
                logger.info(f"  OK {place_name} -> (no coords)")
        else:
            logger.warning(f"  X : {place_name}")

    logger.info(f"[batch_geocode] : {len(results)}/{len(place_names)} ")
    return results


def batch_place_details(
    client: GoogleMapsClient,
    places: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    

    Args:
        client: Google Maps API 
        places: , place_id

    Returns:
        
    """
    logger.info(f"[batch_place_details] : {len(places)} ")

    results = []
    for place in places:
        if not place or not isinstance(place, dict):
            continue

        place_id = place.get('place_id')
        if not place_id:
            #  place_id,
            results.append(place)
            continue

        details = client.get_place_details(place_id)
        if details:
            # 
            merged = {**place, **details}
            results.append(merged)
            logger.info(f"  - {details.get('name')}: rating={details.get('rating', 'N/A')}, price_level={details.get('price_level', 'N/A')}")
        else:
            # ,
            results.append(place)
            logger.warning(f"  - : place_id={place_id}")

    logger.info(f"[batch_place_details] : {len(results)} ()")
    return results


def directions(
    client: GoogleMapsClient,
    origin: str,
    destination: str,
    mode: str = "driving",
    waypoints: Optional[List[str]] = None,
    alternatives: bool = False,
    departure_time: Optional[str] = None,
    verify_waypoints: bool = True  # P0 : waypoint 
) -> Optional[Dict[str, Any]]:
    """
    ( -  waypoint )

    Args:
        client: Google Maps API 
        origin: 
        destination: 
        mode:  (driving, walking, transit, bicycling)
        waypoints:  (,,)
        alternatives:  ( False)
        departure_time:  (ISO)
        verify_waypoints:  waypoints  (P0 )

    Returns:
         {legs: [{steps: [...], distance, duration}], waypoints_verified: bool}  None
    """
    # ( waypoints  intent  trip/routing )
    if not waypoints:
        try:
            from src.tools.local_context_db import ContextManager
            if ContextManager.should_use_local_db():
                db = ContextManager.get_db()
                if db and db.is_connected():
                    routes_data = db.get_routes(origin, destination, mode)
                    if routes_data:
                        summary = routes_data.get('summary', '')
                        logger.info(f"[LOCAL_DB] : {origin} -> {destination} ({mode})")
                        return {
                            'legs': [{
                                'summary': summary,
                                'steps': [],
                            }],
                            'waypoints_verified': True,
                            'summary': summary,
                            'from_local_db': True
                        }
        except Exception as e:
            logger.debug(f"[LOCAL_DB] : {e}")

    waypoints_str = f" via {waypoints}" if waypoints else ""
    logger.info(f"[directions] {origin} -> {destination}{waypoints_str} ({mode})")

    #  : waypoints ,
    geocoded_waypoints = None
    original_waypoints = waypoints  #  waypoint 

    if waypoints:
        geocoded_waypoints = []
        for wp in waypoints:
            #  (lat,lng)
            if ',' in wp and wp.replace(',', '').replace('.', '').replace('-', '').replace(' ', '').isdigit():
                # 
                geocoded_waypoints.append(wp)
            else:
                # 
                logger.info(f"[directions]  waypoint '{wp}' ")
                geocode_result = client.geocode(wp)
                if geocode_result and 'results' in geocode_result and geocode_result['results']:
                    location = geocode_result['results'][0]['geometry']['location']
                    lat_lng = f"{location['lat']},{location['lng']}"
                    geocoded_waypoints.append(lat_lng)
                    logger.info(f"[directions] waypoint '{wp}' -> {lat_lng}")
                else:
                    logger.warning(f"[directions]  waypoint '{wp}' ,")

        if not geocoded_waypoints:
            logger.warning(f"[directions]  waypoints ,")
            geocoded_waypoints = None

    result = client.get_directions(
        origin=origin,
        destination=destination,
        mode=mode,
        waypoints=geocoded_waypoints,
        alternatives=alternatives
    )

    # google_maps.py  {'routes': [...], 'primary': {...}}
    if result and isinstance(result, dict):
        primary = result.get('primary')

        if primary:
            total_distance = primary.get('distance', 0)
            total_duration = primary.get('duration', 0)
            logger.info(f"[directions] , : {total_distance}m, : {total_duration}s")

            #  P0 : waypoints 
            waypoints_verified = True
            if verify_waypoints and original_waypoints:
                waypoints_verified = _verify_waypoints_in_route(primary, original_waypoints)

                if not waypoints_verified:
                    log_highlight_event(
                        logger,
                        event_type='warning',
                        title='Waypoint Verification Failed',
                        details=[
                            f"Requested waypoints: {original_waypoints}",
                            f"Summary: {primary.get('summary', 'N/A')}",
                            "Waypoints may have been ignored by Google Maps API",
                            "Consider using more specific waypoint names or coordinates"
                        ]
                    )

            #  primary ( legs )+ waypoints_verified 
            return {
                'legs': [primary],
                'waypoints_verified': waypoints_verified,
                'summary': primary.get('summary', '')
            }
        else:
            logger.warning("[directions]  (routes)")
            return None
    else:
        logger.warning(f"[directions]  (result={type(result).__name__ if result else 'None'})")
        return None


def _verify_waypoints_in_route(route: Dict[str, Any], waypoints: List[str]) -> bool:
    """
     waypoints (P0 )

    :
    1.  route['summary']  waypoint 
    2.  route['legs'] ( = len(waypoints) + 1)

    Args:
        route: Google Maps API 
        waypoints:  waypoint 

    Returns:
        True  waypoints ,False 
    """
    #  1:  summary 
    summary = route.get('summary', '').lower()
    matched_count = 0

    for wp in waypoints:
        # ( "Road", "Street", "Highway")
        wp_clean = wp.lower()
        for suffix in [' road', ' rd', ' street', ' st', ' highway', ' hwy', ' avenue', ' ave']:
            wp_clean = wp_clean.replace(suffix, '')

        #  summary  waypoint
        if wp_clean and wp_clean in summary:
            matched_count += 1
            logger.debug(f"[_verify_waypoints] OK Waypoint '{wp}' found in summary")
        else:
            logger.debug(f"[_verify_waypoints] X Waypoint '{wp}' NOT found in summary")

    #  2:  legs ( waypoint  leg)
    legs_count = len(route.get('legs', []))
    expected_legs = len(waypoints) + 1

    logger.debug(f"[_verify_waypoints] Legs count: {legs_count}, Expected: {expected_legs}")

    #  50%  waypoints , legs ,
    verification_passed = (matched_count >= len(waypoints) * 0.5) or (legs_count == expected_legs)

    logger.info(f"[_verify_waypoints] Verification result: {'PASSED' if verification_passed else 'FAILED'} "
                f"(matched {matched_count}/{len(waypoints)} waypoints, {legs_count}/{expected_legs} legs)")

    return verification_passed


def distance_matrix(
    client: GoogleMapsClient,
    origins: List[str],
    destinations: List[str],
    mode: str = "driving",
    departure_time: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    

    Args:
        client: Google Maps API 
        origins: 
        destinations: 
        mode: 
        departure_time: 

    Returns:
         {rows: [{elements: [{distance, duration, status}]}]}  None
    """
    # ( intent  trip/routing )
    try:
        from src.tools.local_context_db import ContextManager
        if ContextManager.should_use_local_db():
            db = ContextManager.get_db()
            if db and db.is_connected():
                rows = []
                db_hit_count = 0

                for origin in origins:
                    elements = []
                    for destination in destinations:
                        # 
                        travel_time = db.get_travel_time(origin, destination, mode)

                        if travel_time:
                            db_hit_count += 1
                            # duration_distance : "Travel Time from A to B by car is 14 mins (3.0 km)."
                            elements.append({
                                'duration_distance': travel_time.get('duration_distance', ''),
                                'status': 'OK',
                                'from_local_db': True
                            })
                        else:
                            # , API 
                            elements.append(None)

                    rows.append({'elements': elements})

                # ,
                total_queries = len(origins) * len(destinations)
                if db_hit_count == total_queries:
                    logger.info(f"[LOCAL_DB] : {db_hit_count}/{total_queries}")
                    return {'rows': rows, 'from_local_db': True}
                elif db_hit_count > 0:
                    logger.info(f"[LOCAL_DB] : {db_hit_count}/{total_queries}, API")

    except Exception as e:
        logger.debug(f"[LOCAL_DB] : {e}")

    logger.info(f"[distance_matrix] {len(origins)}  x {len(destinations)}  ({mode})")
    result = client.get_distance_matrix(origins, destinations, mode, departure_time)
    if result:
        logger.info(f"[distance_matrix] ")
    else:
        logger.warning(f"[distance_matrix] ")
    return result


def timezone(
    client: GoogleMapsClient,
    lat: float,
    lng: float,
    timestamp: int
) -> Optional[Dict[str, Any]]:
    """
    

    Args:
        client: Google Maps API 
        lat: 
        lng: 
        timestamp: Unix 

    Returns:
         {timeZoneId, timeZoneName, rawOffset, dstOffset}  None
    """
    logger.info(f"[timezone] : ({lat}, {lng}), : {timestamp}")
    result = client.get_timezone(lat, lng, timestamp)
    if result:
        logger.info(f"[timezone] : {result['timeZoneId']}")
    else:
        logger.warning(f"[timezone] ")
    return result


# ============================================================================
# 
# ============================================================================

def open_at_time(place_detail: Dict[str, Any], local_dt: datetime) -> Optional[bool]:
    """
    

    Args:
        place_detail: ( opening_hours.periods)
        local_dt: 

    Returns:
        True=, False=, None=
    """
    opening_hours = place_detail.get('opening_hours', {})
    periods = opening_hours.get('periods', [])

    if not periods:
        logger.debug(f"[open_at_time] {place_detail.get('name')}: ")
        return None

    # Google Places API  weekday: 0=, 1=, ..., 6=
    # Python datetime.weekday(): 0=, 1=, ..., 6=
    weekday = (local_dt.weekday() + 1) % 7
    time_of_day = local_dt.time()

    for period in periods:
        if 'open' not in period:
            continue

        open_day = period['open'].get('day')
        if open_day != weekday:
            continue

        #  (: "HHMM")
        open_time_str = period['open'].get('time', '0000')
        open_time = dt_time(int(open_time_str[:2]), int(open_time_str[2:]))

        #  close 
        if 'close' in period:
            close_time_str = period['close'].get('time', '2359')
            close_time = dt_time(int(close_time_str[:2]), int(close_time_str[2:]))

            #  ( 23:00 - 02:00)
            if close_time < open_time:
                if time_of_day >= open_time or time_of_day < close_time:
                    logger.debug(f"[open_at_time] {place_detail.get('name')}: ()")
                    return True
            else:
                if open_time <= time_of_day < close_time:
                    logger.debug(f"[open_at_time] {place_detail.get('name')}: ")
                    return True
        else:
            # ,(24?)
            if time_of_day >= open_time:
                logger.debug(f"[open_at_time] {place_detail.get('name')}: (24h?)")
                return True

    logger.debug(f"[open_at_time] {place_detail.get('name')}: ")
    return False


def is_open_at_time_text(
    opening_hours_text: str,
    day_of_week: str,
    target_time: str
) -> Optional[bool]:
    """
    

    Args:
        opening_hours_text:  "Tuesday: 11:00 AM - 9:00 PM"  "Open 24 hours"
        day_of_week: , "Monday", "Tuesday" 
        target_time: , "8:00 PM", "9:15 AM"

    Returns:
        True=, False=, None=
    """
    import re

    if not opening_hours_text:
        return None

    # 24
    if "open 24 hours" in opening_hours_text.lower():
        return True

    # 
    # : "Tuesday: 11:00 AM - 9:00 PM"  "Tuesday: Closed"
    day_pattern = rf'{day_of_week}:\s*([^,]+?)(?:,|$)'
    match = re.search(day_pattern, opening_hours_text, re.IGNORECASE)

    if not match:
        logger.debug(f"[is_open_at_time_text]  {day_of_week} ")
        return None

    hours_text = match.group(1).strip()

    # 
    if hours_text.lower() == 'closed':
        return False

    # 24
    if 'open 24 hours' in hours_text.lower():
        return True

    # :11:00 AM - 9:00 PM
    time_pattern = r'(\d{1,2}):?(\d{2})?\s*(AM|PM)\s*[-\u2013\u2014]\s*(\d{1,2}):?(\d{2})?\s*(AM|PM)'
    time_match = re.search(time_pattern, hours_text, re.IGNORECASE)

    if not time_match:
        logger.debug(f"[is_open_at_time_text] : {hours_text}")
        return None

    # 
    open_hour = int(time_match.group(1))
    open_min = int(time_match.group(2)) if time_match.group(2) else 0
    open_ampm = time_match.group(3).upper()

    # 
    close_hour = int(time_match.group(4))
    close_min = int(time_match.group(5)) if time_match.group(5) else 0
    close_ampm = time_match.group(6).upper()

    # 24
    def to_24h(hour, minute, ampm):
        if ampm == 'AM':
            if hour == 12:
                hour = 0
        else:  # PM
            if hour != 12:
                hour += 12
        return hour * 60 + minute  # 

    open_minutes = to_24h(open_hour, open_min, open_ampm)
    close_minutes = to_24h(close_hour, close_min, close_ampm)

    # 
    target_pattern = r'(\d{1,2}):?(\d{2})?\s*(AM|PM)'
    target_match = re.search(target_pattern, target_time, re.IGNORECASE)

    if not target_match:
        logger.debug(f"[is_open_at_time_text] : {target_time}")
        return None

    target_hour = int(target_match.group(1))
    target_min = int(target_match.group(2)) if target_match.group(2) else 0
    target_ampm = target_match.group(3).upper()
    target_minutes = to_24h(target_hour, target_min, target_ampm)

    # ( 11:00 PM - 1:00 AM)
    if close_minutes < open_minutes:
        # : open   close 
        is_open = target_minutes >= open_minutes or target_minutes < close_minutes
    else:
        # : open  close 
        is_open = open_minutes <= target_minutes < close_minutes

    logger.debug(f"[is_open_at_time_text] {day_of_week} {target_time}: open={open_minutes}min, close={close_minutes}min, target={target_minutes}min -> {'' if is_open else ''}")
    return is_open


def filter_places_by_time(
    places: List[Dict[str, Any]],
    day_of_week: str,
    target_time: str
) -> List[Dict[str, Any]]:
    """
    

    Args:
        places: , address/vicinity 
        day_of_week: , "Monday", "Tuesday"
        target_time: , "8:00 PM", "closed" 

    Returns:
        :
        -  target_time ,
        -  target_time  "closed",
    """
    filtered = []

    # 
    find_closed = target_time.lower() == 'closed'

    for place in places:
        #  opening_hours 
        opening_text = place.get('opening_hours', '')

        if not opening_text:
            #  address  vicinity 
            for field in ['address', 'vicinity', 'information']:
                text = place.get(field, '')
                if text and 'Open:' in text:
                    #  "Open: ..." 
                    open_match = re.search(r'Open:\s*(.+?)(?:\n|$)', text, re.DOTALL)
                    if open_match:
                        opening_text = open_match.group(1)
                        break

        if not opening_text:
            #  "Open:" ,
            for field in ['address', 'vicinity', 'information']:
                text = place.get(field, '')
                if text and day_of_week in text:
                    opening_text = text
                    break

        if find_closed:
            # : "Closed"
            is_closed = _is_closed_on_day(opening_text, day_of_week)
            if is_closed is True:
                filtered.append(place)
            elif is_closed is None:
                # ( closed ,)
                logger.debug(f"[filter_places_by_time] {place.get('name')}: ()")
        else:
            # 
            is_open = is_open_at_time_text(opening_text, day_of_week, target_time)
            if is_open is True:
                filtered.append(place)
            elif is_open is None:
                # ()
                logger.debug(f"[filter_places_by_time] {place.get('name')}: ")

    logger.info(f"[filter_places_by_time] {day_of_week} {target_time}: {len(places)} -> {len(filtered)} {'' if find_closed else ''}")
    return filtered


def _is_closed_on_day(opening_hours_text: str, day_of_week: str) -> Optional[bool]:
    """
    

    Args:
        opening_hours_text: 
        day_of_week: , "Sunday"

    Returns:
        True=, False=, None=
    """
    if not opening_hours_text:
        return None

    # 24
    if "open 24 hours" in opening_hours_text.lower():
        return False  # 24

    # 
    # : "Sunday: Closed"  "Sunday: Closed."  "Sunday: 11:00 AM - 9:00 PM"
    day_pattern = rf'{day_of_week}:\s*([^,]+?)(?:,|$)'
    match = re.search(day_pattern, opening_hours_text, re.IGNORECASE)

    if not match:
        logger.debug(f"[_is_closed_on_day]  {day_of_week} ")
        return None

    hours_text = match.group(1).strip()
    # 
    hours_text = hours_text.rstrip('.;,')

    # 
    if hours_text.lower() == 'closed':
        return True

    # 24
    if 'open 24 hours' in hours_text.lower():
        return False

    # ,
    if '-' in hours_text or '\u2013' in hours_text or '\u2014' in hours_text:
        return False

    return None


def filter_places(
    places: List[Dict[str, Any]],
    min_rating: Optional[float] = None,
    price_level: Optional[int] = None,
    place_types: Optional[List[str]] = None,
    open_at: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """
    

    Args:
        places: 
        min_rating: 
        price_level: (0-4)
        place_types: 
        open_at: (True=, False=, None=)

    Returns:
        
    """
    logger.info(f"[filter_places]  {len(places)} , : rating>={min_rating}, price={price_level}, types={place_types}, open={open_at}")

    filtered = []
    filtered_out_reasons = {}  # 

    for place in places:
        reject_reason = None

        # 
        if min_rating is not None:
            rating = place.get('rating', 0)
            if rating < min_rating:
                reject_reason = f"rating({rating}) < {min_rating}"

        # 
        if reject_reason is None and price_level is not None:
            place_price = place.get('price_level')
            if place_price != price_level:
                reject_reason = f"price_level({place_price}) != {price_level}"

        # 
        if reject_reason is None and place_types:
            place_type_set = set(place.get('types', []))
            if not any(t in place_type_set for t in place_types):
                reject_reason = f"types mismatch"

        # 
        if reject_reason is None and open_at is not None:
            is_open = place.get('open_now', None)
            if is_open != open_at:
                reject_reason = f"open_now({is_open}) != {open_at}"

        if reject_reason:
            filtered_out_reasons[reject_reason] = filtered_out_reasons.get(reject_reason, 0) + 1
        else:
            filtered.append(place)

    logger.info(f"[filter_places]  {len(filtered)} ")

    # 
    if filtered_out_reasons:
        logger.info(f"[filter_places] :")
        for reason, count in filtered_out_reasons.items():
            logger.info(f"  - {reason}: {count} ")

    return filtered


def nearest(
    anchor: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    metric: str = "haversine"
) -> Optional[Dict[str, Any]]:
    """
    

    Args:
        anchor:  {lat, lng, ...}
        candidates:  [{lat, lng, ...}, ...]
        metric:  ('haversine'=, 'travel_time'=)

    Returns:
          None
    """
    if not candidates:
        logger.warning(f"[nearest] ")
        return None

    logger.info(f"[nearest]  {len(candidates)} (: {metric})")

    anchor_lat = anchor.get('lat')
    anchor_lng = anchor.get('lng')

    if anchor_lat is None or anchor_lng is None:
        logger.error(f"[nearest] ")
        return None

    # 
    logger.info(f"[nearest] : {anchor.get('name', 'Unknown')} ({anchor_lat}, {anchor_lng})")

    min_distance = float('inf')
    nearest_place = None

    for place in candidates:
        place_lat = place.get('lat')
        place_lng = place.get('lng')

        if place_lat is None or place_lng is None:
            continue

        if metric == "haversine":
            dist = haversine(anchor_lat, anchor_lng, place_lat, place_lng)
        elif metric == "travel_time":
            #  travel_time ( distance_matrix )
            dist = place.get('travel_time', float('inf'))
        else:
            dist = haversine(anchor_lat, anchor_lng, place_lat, place_lng)

        # ()
        if len(candidates) <= 10:
            logger.info(f"  - {place.get('name', 'Unknown')}: {dist:.2f}m")

        if dist < min_distance:
            min_distance = dist
            nearest_place = place

    if nearest_place:
        logger.info(f"[nearest] : {nearest_place.get('name')}, : {min_distance:.2f}m")
    else:
        logger.warning(f"[nearest] ")

    return nearest_place


def within_radius(
    center: Dict[str, Any],
    radius_m: float,
    candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    

    Args:
        center:  {lat, lng}
        radius_m: ()
        candidates: 

    Returns:
        
    """
    logger.info(f"[within_radius] : ({center.get('lat')}, {center.get('lng')}), : {radius_m}m, : {len(candidates)}")

    center_lat = center.get('lat')
    center_lng = center.get('lng')

    if center_lat is None or center_lng is None:
        logger.error(f"[within_radius] ")
        return []

    within = []
    for place in candidates:
        place_lat = place.get('lat')
        place_lng = place.get('lng')

        if place_lat is None or place_lng is None:
            continue

        dist = haversine(center_lat, center_lng, place_lat, place_lng)
        if dist <= radius_m:
            within.append(place)

    logger.info(f"[within_radius]  {len(within)} ")
    return within


def steps_analysis(route: Dict[str, Any], after: Optional[str] = None) -> Dict[str, Any]:
    """
    ,(,,)

    Args:
        route: ( directions API)
        after: ,( "after Times Square")

    Returns:
         {left_turns, right_turns, roundabouts, next_step, step_after_location, ...}
    """
    logger.info(f"[steps_analysis] " + (f",  '{after}' " if after else ""))

    result = {
        'left_turns': 0,
        'right_turns': 0,
        'roundabouts': [],
        'next_step': None,
        'total_steps': 0,
        'step_after_location': None  # :
    }

    if not route or 'legs' not in route:
        return result

    all_steps = []
    for leg in route['legs']:
        all_steps.extend(leg.get('steps', []))

    result['total_steps'] = len(all_steps)

    #  after ,
    found_location = False
    if after:
        after_lower = after.lower()

    for i, step in enumerate(all_steps):
        maneuver = step.get('maneuver', '') or ''
        html_instructions = (step.get('html_instructions', '') or '').lower()

        #  HTML 
        import re
        clean_instructions = re.sub('<.*?>', '', step.get('html_instructions', ''))

        #  after ,
        if after and not found_location:
            if after_lower in clean_instructions.lower():
                found_location = True
                logger.info(f"[steps_analysis]  '{after}'  {i}")
                # ()
                if i + 1 < len(all_steps):
                    next_step = all_steps[i + 1]
                    distance_data = next_step.get('distance', {})
                    duration_data = next_step.get('duration', {})

                    distance_text = distance_data.get('text', '') if isinstance(distance_data, dict) else str(distance_data) if distance_data else ''
                    duration_text = duration_data.get('text', '') if isinstance(duration_data, dict) else str(duration_data) if duration_data else ''

                    result['step_after_location'] = {
                        'step_index': i + 1,
                        'maneuver': next_step.get('maneuver', ''),
                        'instruction': next_step.get('html_instructions', ''),
                        'distance': distance_text,
                        'duration': duration_text
                    }
                    logger.info(f"[steps_analysis]  '{after}' : {clean_instructions[:50]}...")

        # 
        if 'turn-left' in maneuver or 'left' in html_instructions:
            result['left_turns'] += 1

        # 
        if 'turn-right' in maneuver or 'right' in html_instructions:
            result['right_turns'] += 1

        # 
        if 'roundabout' in maneuver or 'roundabout' in html_instructions:
            # 
            exit_match = re.search(r'take\s+the\s+(\d+)(?:st|nd|rd|th)?\s+exit', html_instructions)
            if exit_match:
                exit_num = int(exit_match.group(1))
                result['roundabouts'].append({
                    'step_index': i,
                    'exit': exit_num,
                    'instruction': step.get('html_instructions', '')
                })

        # ()
        if i == 0:
            #  distance  duration()
            distance_data = step.get('distance', {})
            duration_data = step.get('duration', {})

            distance_text = distance_data.get('text', '') if isinstance(distance_data, dict) else str(distance_data) if distance_data else ''
            duration_text = duration_data.get('text', '') if isinstance(duration_data, dict) else str(duration_data) if duration_data else ''

            result['next_step'] = {
                'maneuver': maneuver,
                'instruction': step.get('html_instructions', ''),
                'distance': distance_text,
                'duration': duration_text
            }

    # ,
    if after and not found_location:
        logger.warning(f"[steps_analysis]  '{after}'")

    logger.info(f"[steps_analysis] : {result['left_turns']}, {result['right_turns']}, {len(result['roundabouts'])}")
    return result


def pairwise_extremes(
    locations: List[Dict[str, Any]],
    metric: str = "haversine"
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], float]:
    """
    

    Args:
        locations:  [{lat, lng, name, ...}, ...]
        metric:  ('haversine')

    Returns:
        (1, 2, )
    """
    logger.info(f"[pairwise_extremes]  {len(locations)} ")

    if len(locations) < 2:
        logger.warning(f"[pairwise_extremes] 2")
        return None, None, 0.0

    max_distance = 0.0
    farthest_pair = (None, None)

    for i in range(len(locations)):
        for j in range(i + 1, len(locations)):
            loc1 = locations[i]
            loc2 = locations[j]

            if metric == "haversine":
                dist = haversine(
                    loc1.get('lat'), loc1.get('lng'),
                    loc2.get('lat'), loc2.get('lng')
                )
            else:
                dist = 0.0

            if dist > max_distance:
                max_distance = dist
                farthest_pair = (loc1, loc2)

    logger.info(f"[pairwise_extremes] : {farthest_pair[0].get('name')} <-> {farthest_pair[1].get('name')}, : {max_distance:.2f}m")
    return farthest_pair[0], farthest_pair[1], max_distance


def tsp_tw(
    distance_matrix_data: Dict[str, Any],
    locations: List[Dict[str, Any]],
    service_times: Optional[List[float]] = None,
    time_windows: Optional[List[Tuple[int, int]]] = None,
    start_time: Optional[str] = None,
    time_budget: Optional[float] = None,
    mode: str = "driving"
) -> Dict[str, Any]:
    """
    (TSP-TW)

    Args:
        distance_matrix_data: ( distance_matrix API)
        locations: 
        service_times: ()
        time_windows:  [(, ), ...]
        start_time: (ISO)
        time_budget: ()
        mode:  (driving/walking/bicycling/transit)

    Returns:
         {order, total_time, total_distance, feasible}
    """
    logger.info(f"[tsp_tw]  {len(locations)} ")

    #  TripOptimizer
    optimizer = TripOptimizer()

    #  (TripOptimizer  List[List[Dict]] )
    distance_matrix = []
    if distance_matrix_data and 'rows' in distance_matrix_data:
        for row in distance_matrix_data['rows']:
            dist_row = []
            for element in row['elements']:
                if element['status'] == 'OK':
                    dist_row.append({
                        'distance': element['distance']['value'],  # 
                        'duration': element['duration']['value']   # 
                    })
                else:
                    dist_row.append(None)  # 
            distance_matrix.append(dist_row)
    else:
        # , haversine 
        #  : 
        # : Haversine , 1.3-1.5 
        # ""( / )
        speed_map = {
            'driving': 25,     #  30-40 km/h, 1.2-1.5
            'walking': 3.5,    #  5 km/h, ~1.4
            'bicycling': 10,   #  15 km/h, ~1.5
            'transit': 15      #  25 km/h,
        }
        avg_speed_kmh = speed_map.get(mode, 25)
        logger.info(f"[tsp_tw]  Haversine ,: {mode},: {avg_speed_kmh} km/h ()")

        distance_matrix = []
        for loc1 in locations:
            row = []
            for loc2 in locations:
                if loc1 == loc2:
                    row.append({'distance': 0, 'duration': 0})
                else:
                    lat1, lng1 = _get_lat_lng(loc1)
                    lat2, lng2 = _get_lat_lng(loc2)

                    dist = haversine(lat1, lng1, lat2, lng2)
                    # 
                    time_sec = dist / (avg_speed_kmh * 1000) * 3600
                    row.append({
                        'distance': int(dist),
                        'duration': int(time_sec)
                    })
            distance_matrix.append(row)

    #  location_names  visit_durations
    location_names = [
        loc.name if hasattr(loc, 'name') else loc.get('name', f'Location {i}')
        for i, loc in enumerate(locations)
    ]

    visit_durations_dict = None
    if service_times:
        visit_durations_dict = {name: duration for name, duration in zip(location_names, service_times)}

    # 
    logger.info(f"[tsp_tw] : {len(distance_matrix)}x{len(distance_matrix[0]) if distance_matrix else 0}")
    logger.info(f"[tsp_tw] : {location_names}")
    if visit_durations_dict:
        logger.info(f"[tsp_tw] : {visit_durations_dict}")
    if time_budget:
        logger.info(f"[tsp_tw] : {time_budget}")

    # 
    try:
        result = optimizer.optimize_trip(
            distance_matrix=distance_matrix,
            location_names=location_names,
            visit_durations=visit_durations_dict,
            start_location_idx=0,
            total_time_available=time_budget,
            start_time=start_time
        )

        # P1-1: TripOptimizertsp_tw
        transformed_result = {
            'order': result.get('location_order'),  # location_order -> order
            'total_time_minutes': result.get('total_time_seconds', 0) / 60,  # 
            'total_distance_km': result.get('total_distance_meters', 0) / 1000,  # 
            'feasible': result.get('feasible', False),
            'route': result.get('route'),  # route
            'greedy_solution': result.get('greedy_solution', False),  # 
            'feasible_locations': result.get('feasible_locations', len(locations)),  # 
        }

        # ,
        if 'error' in result:
            transformed_result['error'] = result['error']
        if 'suggestion' in result:
            transformed_result['suggestion'] = result['suggestion']

        logger.info(f"[tsp_tw] : ={transformed_result.get('order')}, ={transformed_result.get('total_time_minutes'):.1f}")

        # 
        logger.info(f"[tsp_tw] :")
        logger.info(f"  - : {transformed_result.get('order')}")
        logger.info(f"  - : {transformed_result.get('total_distance_km', 0):.2f}km")
        logger.info(f"  - : {transformed_result.get('total_time_minutes', 0):.1f}")
        logger.info(f"  - : {transformed_result.get('feasible', False)}")
        if transformed_result.get('greedy_solution'):
            logger.info(f"  - :  {transformed_result.get('feasible_locations')} ")

        return transformed_result
    except Exception as e:
        logger.error(f"[tsp_tw] : {e}")
        return {
            'order': list(range(len(locations))),
            'total_time': 0,
            'total_distance': 0,
            'feasible': False,
            'error': str(e)
        }


def service_area(
    client: GoogleMapsClient,
    origins: List[Dict[str, Any]],
    time_threshold: float,
    mode: str = "driving"
) -> List[Dict[str, Any]]:
    """
    (): ,

    ,

    Args:
        client: Google Maps API 
        origins:  [{lat, lng, name, ...}, ...]
        time_threshold: ()
        mode: 

    Returns:
        
    """
    logger.info(f"[service_area]  {len(origins)} , {time_threshold}")

    # : (isochrone),
    #  distance_matrix 

    logger.warning(f"[service_area] ,")
    return []


def compare_routes(routes: List[Dict[str, Any]], metric: str = "duration", mode: str = "min") -> int:
    """
    ,

    Args:
        routes: ( directions API)
        metric:  ("distance"  "duration")
        mode: "min" ()  "max" ()

    Returns:
        (0-based)
    """
    logger.info(f"[compare_routes]  {len(routes)}  | metric={metric}, mode={mode}")

    if not routes:
        logger.warning("[compare_routes] ")
        return 0

    # 
    values = []
    for i, route in enumerate(routes):
        # P0: 
        if route is None or not isinstance(route, dict):
            logger.warning(f"[compare_routes]  {i} : {type(route)}")
            values.append(float('inf') if mode == "min" else float('-inf'))
            continue

        if 'legs' not in route or not route['legs']:
            values.append(float('inf') if mode == "min" else float('-inf'))
            continue

        leg = route['legs'][0]

        if metric == "duration":
            value = _extract_metric_value(leg.get('duration'), default=float('inf'))
        elif metric == "distance":
            value = _extract_metric_value(leg.get('distance'), default=float('inf'))
        else:
            logger.warning(f"[compare_routes] : {metric}")
            value = float('inf')

        values.append(value)
        logger.info(f"[compare_routes]    {i}: {metric}={value}")

    # 
    if mode == "min":
        best_index = values.index(min(values))
    else:
        best_index = values.index(max(values))

    logger.info(f"[compare_routes] :  {best_index}, {metric}={values[best_index]}")
    return best_index


def filter_routes(routes: List[Dict[str, Any]], condition: str, keyword: str) -> int:
    """
    ,

    Args:
        routes: ( directions API)
        condition:  ("contains", "contains_multiple" )
        keyword: ( "stairs", "toll", "roundabout")

    Returns:
        (0-based)
    """
    logger.info(f"[filter_routes]  | condition={condition}, keyword={keyword}")

    for i, route in enumerate(routes):
        if route is None or 'legs' not in route:
            continue

        # 
        keyword_count = 0
        for leg in route['legs']:
            for step in leg.get('steps', []):
                instruction = step.get('html_instructions', '').lower()
                if keyword.lower() in instruction:
                    keyword_count += 1

        logger.info(f"[filter_routes]    {i}:  '{keyword}'  {keyword_count} ")

        # 
        if condition == "contains" and keyword_count > 0:
            logger.info(f"[filter_routes] :  {i}")
            return i
        elif condition == "contains_multiple" and keyword_count > 1:
            logger.info(f"[filter_routes] :  {i} ()")
            return i

    logger.warning(f"[filter_routes] , 0")
    return 0


def extract_distance(route: Dict[str, Any]) -> float:
    """
    ()

    Args:
        route: ( directions API)

    Returns:
        ()
    """
    if not route or 'legs' not in route or not route['legs']:
        logger.warning("[extract_distance] ")
        return 0.0

    total_distance = sum(_extract_metric_value(leg.get('distance', 0)) for leg in route['legs'])

    logger.info(f"[extract_distance] : {total_distance}  ({total_distance/1000:.2f} km)")
    return total_distance


def extract_duration(route: Dict[str, Any]) -> float:
    """
    ()

    Args:
        route: ( directions API)

    Returns:
        ()
    """
    if not route or 'legs' not in route or not route['legs']:
        logger.warning("[extract_duration] ")
        return 0.0

    total_duration = sum(_extract_metric_value(leg.get('duration', 0)) for leg in route['legs'])

    logger.info(f"[extract_duration] : {total_duration}  ({total_duration/60:.2f} )")
    return total_duration


def calculate_finish_time(
    client: GoogleMapsClient,
    start_time: str,
    locations: List[Dict[str, Any]],
    stay_durations: List[int],
    mode: str = "driving"
) -> str:
    """
    ( - )

     Trip ,.
     directions API .

    Args:
        client: Google Maps API 
        start_time: (24 , "09:00")
        locations: (), lat/lng
        stay_durations: (), = len(locations) - 1
        mode: (driving/walking/transit/bicycling)

    Returns:
        (24 , "15:00")

    Example:
        >>> locations = [
        ...     {"name": "Rimrock Resort", "lat": 51.15, "lng": -115.57},
        ...     {"name": "Lake Louise", "lat": 51.42, "lng": -116.21},
        ...     {"name": "Moraine Lake", "lat": 51.32, "lng": -116.18}
        ... ]
        >>> calculate_finish_time(client, "09:00", locations, [180, 180], "driving")
        "15:36"  # 9:00 AM + 25min travel + 3h stay + 12min travel + 3h stay
    """
    from datetime import datetime, timedelta

    try:
        # P0+: 
        if isinstance(start_time, (int, float)):
            #  -> "HH:MM"
            # : 9.0 -> "09:00", 9.5 -> "09:30", 14.25 -> "14:15"
            hours = int(start_time)
            minutes = int((start_time - hours) * 60)
            start_time_str = f"{hours:02d}:{minutes:02d}"
            logger.info(f"[calculate_finish_time] : {start_time} ({type(start_time).__name__}) -> {start_time_str}")
        elif not isinstance(start_time, str):
            #  -> 
            start_time_str = str(start_time)
            logger.warning(f"[calculate_finish_time] : {type(start_time).__name__} -> {start_time_str}")
        else:
            start_time_str = start_time

        # 
        current_time = datetime.strptime(start_time_str, "%H:%M")

        logger.info(f"[calculate_finish_time]  | : {start_time_str} | : {len(locations)} | : {mode}")

        # 
        for i in range(len(locations) - 1):
            origin = locations[i]
            destination = locations[i + 1]

            # 
            origin_coords = f"{origin['lat']},{origin['lng']}"
            dest_coords = f"{destination['lat']},{destination['lng']}"

            logger.info(f"[calculate_finish_time]  {i+1}/{len(locations)-1}: {origin.get('name', 'Unknown')} -> {destination.get('name', 'Unknown')}")

            route = directions(client, origin_coords, dest_coords, mode=mode)

            if route and 'legs' in route and route['legs']:
                travel_seconds = route['legs'][0].get('duration', 0)
                travel_minutes = travel_seconds / 60
                logger.info(f"  - : {travel_minutes:.1f}  ({travel_seconds} )")
            else:
                # : Haversine 
                dist_m = haversine(origin['lat'], origin['lng'], destination['lat'], destination['lng'])
                # :driving=50km/h, walking=5km/h
                speed_kmh = 50 if mode == "driving" else 5
                travel_minutes = (dist_m / 1000) / speed_kmh * 60
                logger.warning(f"  - , Haversine : {travel_minutes:.1f} ")

            # 
            current_time += timedelta(minutes=travel_minutes)

            # ()
            if i < len(stay_durations):
                stay_min = stay_durations[i]
                current_time += timedelta(minutes=stay_min)
                logger.info(f"  - : {stay_min} ")

        # 
        finish_time = current_time.strftime("%H:%M")

        logger.info(f"[calculate_finish_time]  | : {start_time_str} -> : {finish_time}")

        return finish_time

    except Exception as e:
        logger.error(f"[calculate_finish_time] : {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "00:00"


def calculate_arrival_time(
    departure_time: str,
    travel_durations: List[float],
    params: dict = {},
    mode: str = 'driving'
) -> Dict[str, Any]:
    """
    

     Trip ,.

    Args:
        departure_time: (24 , "09:00")
        travel_durations: (),
        params: 
        mode: 

    Returns:
        {
            "arrival_time": "HH:MM",
            "total_travel_minutes": float
        }

    Example:
        >>> calculate_arrival_time("09:00", [30, 16])
        {"arrival_time": "09:46", "total_travel_minutes": 46}
    """
    from datetime import datetime, timedelta

    try:
        # 
        dt = datetime.strptime(departure_time, "%H:%M")

        # 
        total_minutes = sum(travel_durations)
        dt += timedelta(minutes=total_minutes)

        arrival_time = dt.strftime("%H:%M")

        logger.info(f"[calculate_arrival_time] {departure_time} + {total_minutes}min = {arrival_time}")

        return {
            "arrival_time": arrival_time,
            "total_travel_minutes": total_minutes
        }
    except Exception as e:
        logger.error(f"[calculate_arrival_time] Error: {e}")
        return {
            "arrival_time": "00:00",
            "total_travel_minutes": 0
        }


def add_durations(durations: List[Any]) -> Dict[str, Any]:
    """
    

     Trip ,.

    Args:
        durations: ,:
            - ()
            - ( 'value'  duration )
            - 

    Returns:
        {
            "total_seconds": float,      # 
            "total_minutes": float,      # 
            "total_hours": float,        # 
            "formatted": str             # ( "2h 30min")
        }

    Example:
        >>> add_durations([1800, 2400, 900])  # 
        {"total_seconds": 5100, "total_minutes": 85, "total_hours": 1.42, "formatted": "1h 25min"}

        >>> add_durations([{"value": 30, "unit": "mins"}, {"value": 45, "unit": "mins"}])
        {"total_seconds": 4500, "total_minutes": 75, "total_hours": 1.25, "formatted": "1h 15min"}
    """
    logger.info(f"[add_durations]  {len(durations)} ")

    total_seconds = 0.0
    valid_count = 0
    zero_count = 0

    for i, duration in enumerate(durations):
        if duration is None:
            logger.warning(f"[add_durations]  {i}  None,")
            continue

        # ( directions API)
        if isinstance(duration, dict):
            value = _extract_metric_value(duration, default=0)
            if value == 0:
                zero_count += 1
                logger.warning(f"[add_durations]  {i}: 0 (API)")
            else:
                valid_count += 1
                logger.debug(f"[add_durations]  {i}: {value} ()")
            total_seconds += value

        # 
        elif isinstance(duration, (int, float)):
            if duration == 0:
                zero_count += 1
                logger.warning(f"[add_durations]  {i}: 0(API)")
            else:
                #  3600 ,()
                if duration > 3600:
                    total_seconds += duration
                    valid_count += 1
                    logger.debug(f"[add_durations]  {i}: {duration} ")
                else:
                    total_seconds += duration * 60  # 
                    valid_count += 1
                    logger.debug(f"[add_durations]  {i}: {duration}  = {duration * 60} ")
        else:
            logger.warning(f"[add_durations]  {i} : {type(duration)}")

    # 0,
    if zero_count > 0 and valid_count == 0:
        logger.error(f"[add_durations] WARNING  {zero_count} 0,(directions/geocode)")

    # 
    total_minutes = total_seconds / 60
    total_hours = total_seconds / 3600

    # 
    hours = int(total_hours)
    minutes = int((total_hours - hours) * 60)

    if hours > 0:
        formatted = f"{hours}h {minutes}min" if minutes > 0 else f"{hours}h"
    else:
        formatted = f"{int(total_minutes)}min"

    result = {
        "total_seconds": total_seconds,
        "total_minutes": total_minutes,
        "total_hours": round(total_hours, 2),
        "formatted": formatted
    }

    logger.info(f"[add_durations] : {formatted} ({total_seconds} )")

    return result


def count_in_route(route: Dict[str, Any], keyword: str) -> int:
    """
    

     Routing ,(,).

    Args:
        route: ( directions API)
        keyword: ( "turn", "left", "right", "roundabout")

    Returns:
        

    Example:
        >>> count_in_route(route, "left")
        3  #  3 
    """
    logger.info(f"[count_in_route]  '{keyword}' ")

    if not route or 'legs' not in route or not route['legs']:
        logger.warning("[count_in_route] ")
        return 0

    count = 0
    keyword_lower = keyword.lower()

    for leg_idx, leg in enumerate(route['legs']):
        for step_idx, step in enumerate(leg.get('steps', [])):
            #  HTML 
            html_instructions = step.get('html_instructions', '')
            #  HTML 
            import re
            clean_instructions = re.sub('<.*?>', '', html_instructions).lower()

            # 
            occurrences = clean_instructions.count(keyword_lower)
            if occurrences > 0:
                count += occurrences
                logger.debug(f"[count_in_route] Leg {leg_idx}, Step {step_idx}:  {occurrences} ")

    logger.info(f"[count_in_route] : '{keyword}'  {count} ")

    return count


def feasibility_check(
    start_time: str,
    available_time: int,  # minutes
    travel_durations: List[float],
    stay_durations: List[int],
    params: dict = {},
    mode: str = 'driving'
) -> Dict[str, Any]:
    """
    

     Trip ("How many places can I visit?"),
    .

    Args:
        start_time:  (HH:MM)
        available_time:  ()
        travel_durations:  ()
        stay_durations:  ()
        params: 
        mode: 

    Returns:
        {
            "feasible_count": int,
            "feasible_places": List[int],  // 
            "total_time_minutes": float,
            "remaining_time_minutes": float
        }

    Example:
        >>> feasibility_check("09:00", 360, [30, 16, 25], [90, 90, 60])
        {
            "feasible_count": 2,
            "feasible_places": [0, 1],
            "total_time_minutes": 226,
            "remaining_time_minutes": 134
        }
    """
    from datetime import datetime, timedelta

    try:
        # 
        dt = datetime.strptime(start_time, "%H:%M")

        feasible_count = 0
        feasible_places = []
        cumulative_time = 0.0

        # 
        for i, (travel_dur, stay_dur) in enumerate(zip(travel_durations, stay_durations)):
            # 
            time_needed = travel_dur + stay_dur

            # ,
            if cumulative_time + time_needed > available_time:
                break

            feasible_count += 1
            feasible_places.append(i)
            cumulative_time += time_needed

        remaining_time = available_time - cumulative_time

        logger.info(f"[feasibility_check]  {feasible_count} , {remaining_time:.1f} ")
        logger.info(f"  : {start_time}, : {available_time}min")
        logger.info(f"  : {travel_durations}")
        logger.info(f"  : {stay_durations}")

        return {
            "feasible_count": feasible_count,
            "feasible_places": feasible_places,
            "total_time_minutes": cumulative_time,
            "remaining_time_minutes": remaining_time
        }

    except Exception as e:
        logger.error(f"[feasibility_check] Error: {e}")
        return {
            "feasible_count": 0,
            "feasible_places": [],
            "total_time_minutes": 0.0,
            "remaining_time_minutes": available_time
        }


def calculate_latest_visit_time(
    departure_time: str,
    travel_duration: float,
    params: dict = {},
    mode: str = 'driving'
) -> Dict[str, Any]:
    """
    ()

     Trip ,:
    " 9:00 AM  B, A?"
     = 9:00 AM - travel_duration

    Args:
        departure_time: (24 , "09:00")
        travel_duration: ()
        params: 
        mode: 

    Returns:
        {
            "latest_visit_time": "HH:MM",
            "travel_duration_minutes": float
        }

    Example:
        >>> calculate_latest_visit_time("09:00", 30.0)
        {
            "latest_visit_time": "08:30",
            "travel_duration_minutes": 30.0
        }
    """
    from datetime import datetime, timedelta

    try:
        # 
        dt = datetime.strptime(departure_time, "%H:%M")

        # : -  = 
        dt -= timedelta(minutes=travel_duration)
        latest_time = dt.strftime("%H:%M")

        logger.info(f"[calculate_latest_visit_time] {departure_time} - {travel_duration}min = {latest_time}")

        return {
            "latest_visit_time": latest_time,
            "travel_duration_minutes": travel_duration
        }

    except Exception as e:
        logger.error(f"[calculate_latest_visit_time] Error: {e}")
        return {
            "latest_visit_time": None,
            "travel_duration_minutes": 0.0
        }


def calculate_latest_departure(
    client: GoogleMapsClient,
    closing_time: str,
    locations: List[Dict[str, Any]],
    stay_durations: List[int],
    mode: str = "driving"
) -> str:
    """
    ()- P0 

     Trip ,.
    :" A(30min),B(1h),C(2h),C  5:00 PM ,?"

    Args:
        client: Google Maps API 
        closing_time: (24 , "17:00")
        locations: (), lat/lng
        stay_durations: (), = len(locations) - 1
        mode: (driving/walking/transit/bicycling)

    Returns:
        (24 , "13:25")

    Example:
        >>> locations = [
        ...     {"name": "Home", "lat": -33.87, "lng": 151.21},
        ...     {"name": "The Rocks", "lat": -33.86, "lng": 151.21},
        ...     {"name": "Bondi Beach", "lat": -33.89, "lng": 151.27},
        ...     {"name": "Royal Botanic Garden", "lat": -33.86, "lng": 151.22}
        ... ]
        >>> calculate_latest_departure(client, "17:00", locations, [30, 60, 120], "driving")
        "13:37"  #  5:00 PM :-2h() -15min() -1h() -20min() -30min() -10min()
    """
    from datetime import datetime, timedelta

    try:
        # 
        current_time = datetime.strptime(closing_time, "%H:%M")

        logger.info(f"[calculate_latest_departure]  | : {closing_time} | : {len(locations)} | : {mode}")

        # 
        for i in range(len(locations) - 1, 0, -1):
            origin = locations[i - 1]
            destination = locations[i]

            # ()
            if i - 1 < len(stay_durations):
                stay_min = stay_durations[i - 1]
                current_time -= timedelta(minutes=stay_min)
                logger.info(f"[calculate_latest_departure]  {i}/{len(locations)-1}:  {stay_min} ")

            # 
            origin_coords = f"{origin['lat']},{origin['lng']}"
            dest_coords = f"{destination['lat']},{destination['lng']}"

            logger.info(f"[calculate_latest_departure]  {i}/{len(locations)-1}: {origin.get('name', 'Unknown')} -> {destination.get('name', 'Unknown')}")

            route = directions(client, origin_coords, dest_coords, mode=mode)

            if route and 'legs' in route and route['legs']:
                travel_seconds = route['legs'][0].get('duration', 0)
                travel_minutes = travel_seconds / 60
                logger.info(f"  - : {travel_minutes:.1f}  ({travel_seconds} )")
            else:
                # : Haversine 
                dist_m = haversine(origin['lat'], origin['lng'], destination['lat'], destination['lng'])
                # :driving=50km/h, walking=5km/h
                speed_kmh = 50 if mode == "driving" else 5
                travel_minutes = (dist_m / 1000) / speed_kmh * 60
                logger.warning(f"  - , Haversine : {travel_minutes:.1f} ")

            # 
            current_time -= timedelta(minutes=travel_minutes)

        # 
        latest_departure = current_time.strftime("%H:%M")

        logger.info(f"[calculate_latest_departure]  | : {closing_time} -> : {latest_departure}")

        return latest_departure

    except Exception as e:
        logger.error(f"[calculate_latest_departure] : {e}")
        import traceback
        logger.error(traceback.format_exc())
        return "00:00"


# ============================================================================
# 
# ============================================================================

OPERATOR_REGISTRY = {
    #  (Phase 2)
    'query_local_place': query_local_place,
    'query_local_coordinates': query_local_coordinates,
    'query_local_routes': query_local_routes,
    'query_local_travel_time': query_local_travel_time,
    'query_local_places_batch': query_local_places_batch,
    'query_local_nearby_places': query_local_nearby_places,

    #  API
    'geocode': geocode,
    'batch_geocode': batch_geocode,
    'reverse_geocode': reverse_geocode,
    'place_search': place_search,
    'place_details': place_details,
    'batch_place_details': batch_place_details,
    'directions': directions,
    'distance_matrix': distance_matrix,
    'timezone': timezone,
    'haversine': haversine,
    'bearing': bearing,
    'bearing_to_direction': bearing_to_direction,

    # 
    'open_at_time': open_at_time,
    'is_open_at_time_text': is_open_at_time_text,
    'filter_places_by_time': filter_places_by_time,
    'filter_places': filter_places,
    'nearest': nearest,
    'within_radius': within_radius,
    'steps_analysis': steps_analysis,
    'pairwise_extremes': pairwise_extremes,
    'tsp_tw': tsp_tw,
    'service_area': service_area,

    # Routing 
    'compare_routes': compare_routes,
    'filter_routes': filter_routes,
    'extract_distance': extract_distance,
    'extract_duration': extract_duration,
    'count_in_route': count_in_route,
    'calculate_travel_time': extract_duration,  # ,

    # Trip 
    'calculate_finish_time': calculate_finish_time,
    'calculate_arrival_time': calculate_arrival_time,
    'calculate_latest_visit_time': calculate_latest_visit_time,
    'calculate_latest_departure': calculate_latest_departure,  # P0 
    'feasibility_check': feasibility_check,
    'add_durations': add_durations,
}


def get_operator(name: str):
    """"""
    return OPERATOR_REGISTRY.get(name)


def get_available_operators() -> list:
    """
    

     Planner prompt 

    Returns:
        ()
    """
    return sorted(OPERATOR_REGISTRY.keys())


def validate_operator(name: str) -> bool:
    """
    

    Args:
        name: 

    Returns:
        True ,False 
    """
    return name in OPERATOR_REGISTRY
