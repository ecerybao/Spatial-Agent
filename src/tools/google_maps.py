import googlemaps
import os
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class GoogleMapsClient:
    """Google Maps API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            raise ValueError("Google Maps API key is required")
        self.client = googlemaps.Client(key=self.api_key)

    def geocode(
        self,
        address: str,
        location_bias: Optional[Tuple[float, float]] = None,
        region: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        :

        Args:
            address: 
            location_bias:  (lat, lng),
                         ,
            region: (), 'bd', 'ae', 'uk',

        Returns:
             {lat, lng, formatted_address, place_id}  None
        """
        try:
            #  API 
            params = {}
            if region:
                params['region'] = region
                logger.debug(f"Using region bias: {region}")

            #  Google Geocoding API()
            results = self.client.geocode(address, **params)

            if not results:
                return None

            #  location_bias,
            if not location_bias:
                result = results[0]
                return {
                    'lat': result['geometry']['location']['lat'],
                    'lng': result['geometry']['location']['lng'],
                    'formatted_address': result['formatted_address'],
                    'place_id': result['place_id']
                }

            #  location_bias,
            anchor_lat, anchor_lng = location_bias
            logger.debug(f"Using location bias: ({anchor_lat}, {anchor_lng}), found {len(results)} candidates")

            from ..utils.optimization import haversine

            # ( haversine )
            min_distance = float('inf')
            closest_result = None

            for result in results:
                result_lat = result['geometry']['location']['lat']
                result_lng = result['geometry']['location']['lng']
                #  haversine (),
                distance = haversine(anchor_lat, anchor_lng, result_lat, result_lng) / 1000

                if distance < min_distance:
                    min_distance = distance
                    closest_result = result

            if closest_result:
                logger.debug(f"Selected closest result: {min_distance:.1f}km from anchor")

                # :
                import re

                #  1: Plus Code ( "QCV4+98V"), 200km()
                if re.match(r'^[A-Z0-9]{4,}\+[A-Z0-9]{2,}', address):
                    max_threshold = 200
                    logger.debug(f"Plus Code detected: {address}, using {max_threshold}km threshold")

                #  2: (,)
                # :3,
                elif len(closest_result['formatted_address'].split(',')) <= 2:
                    max_threshold = 200
                    logger.debug("Cross-city query detected, using 200km threshold")

                #  3: , 100km
                else:
                    max_threshold = 100

                if min_distance > max_threshold:
                    logger.warning(
                        f"Geocoding result too far from anchor: {min_distance:.1f}km > {max_threshold}km. "
                        f"Rejecting: {closest_result['formatted_address']}"
                    )
                    return None  # 

                return {
                    'lat': closest_result['geometry']['location']['lat'],
                    'lng': closest_result['geometry']['location']['lng'],
                    'formatted_address': closest_result['formatted_address'],
                    'place_id': closest_result['place_id']
                }

            return None
        except Exception as e:
            logger.error(f"Geocoding error for {address}: {e}")
            return None

    def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        """:"""
        try:
            results = self.client.reverse_geocode((lat, lng))
            if results:
                return results[0]['formatted_address']
            return None
        except Exception as e:
            logger.error(f"Reverse geocoding error for {lat}, {lng}: {e}")
            return None

    def nearby_search(self, location: Tuple[float, float], radius: int = 5000,
                     place_type: str = None, keyword: str = None,
                     min_rating: float = None, open_now: bool = False) -> List[Dict[str, Any]]:
        """"""
        try:
            results = self.client.places_nearby(
                location=location,
                radius=radius,
                type=place_type,
                keyword=keyword,
                open_now=open_now
            )

            places = []
            for place in results.get('results', []):
                rating = place.get('rating', 0)
                if min_rating and rating < min_rating:
                    continue

                places.append({
                    'name': place['name'],
                    'place_id': place['place_id'],
                    'lat': place['geometry']['location']['lat'],
                    'lng': place['geometry']['location']['lng'],
                    'rating': rating,
                    'user_ratings_total': place.get('user_ratings_total', 0),
                    'price_level': place.get('price_level'),
                    'types': place.get('types', []),
                    'vicinity': place.get('vicinity', ''),
                    'open_now': place.get('opening_hours', {}).get('open_now', False)
                })

            # 
            places.sort(key=lambda x: (x['rating'], x['user_ratings_total']), reverse=True)
            return places

        except Exception as e:
            logger.error(f"Nearby search error: {e}")
            return []

    def get_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """"""
        try:
            result = self.client.place(place_id=place_id)
            if result['status'] == 'OK':
                place = result['result']
                return {
                    'name': place['name'],
                    'place_id': place['place_id'],
                    'lat': place['geometry']['location']['lat'],
                    'lng': place['geometry']['location']['lng'],
                    'formatted_address': place.get('formatted_address', ''),
                    'rating': place.get('rating'),
                    'user_ratings_total': place.get('user_ratings_total'),
                    'price_level': place.get('price_level'),
                    'opening_hours': place.get('opening_hours'),
                    'formatted_phone_number': place.get('formatted_phone_number'),
                    'website': place.get('website'),
                    'types': place.get('types', [])
                }
            return None
        except Exception as e:
            logger.error(f"Place details error for {place_id}: {e}")
            return None

    def get_directions(self, origin: str, destination: str,
                      mode: str = "driving", waypoints: List[str] = None,
                      optimize_waypoints: bool = False,
                      alternatives: bool = False) -> Optional[Dict[str, Any]]:
        """"""
        try:
            # ()
            logger.info(f"[directions]  API: {origin} -> {destination} (mode={mode}, waypoints={waypoints})")

            result = self.client.directions(
                origin=origin,
                destination=destination,
                mode=mode,
                waypoints=waypoints,
                optimize_waypoints=optimize_waypoints,
                alternatives=alternatives
            )

            if not result:
                return None

            routes: List[Dict[str, Any]] = []
            for route in result:
                legs = route.get('legs') or []
                if not legs:
                    continue
                leg = legs[0]
                steps = []
                for step in leg.get('steps', []):
                    steps.append({
                        'html_instructions': step.get('html_instructions'),
                        'distance': step.get('distance', {}).get('text'),
                        'duration': step.get('duration', {}).get('text'),
                        'maneuver': step.get('maneuver'),
                    })

                routes.append({
                    'distance': leg.get('distance', {}).get('value'),
                    'duration': leg.get('duration', {}).get('value'),
                    'distance_text': leg.get('distance', {}).get('text'),
                    'duration_text': leg.get('duration', {}).get('text'),
                    'start_address': leg.get('start_address'),
                    'end_address': leg.get('end_address'),
                    'steps': steps,
                    'overview_polyline': route.get('overview_polyline', {}).get('points'),
                    'summary': route.get('summary'),
                })

            if not routes:
                return None

            return {
                'routes': routes,
                'primary': routes[0]
            }
        except Exception as e:
            logger.error(f"Directions error from {origin} to {destination}: {e}")
            return None

    def text_search(self, query: str, location: Tuple[float, float] = None,
                   radius: int = 50000) -> List[Dict[str, Any]]:
        """"""
        try:
            results = self.client.places(
                query=query,
                location=location,
                radius=radius
            )

            places = []
            for place in results.get('results', []):
                places.append({
                    'name': place['name'],
                    'place_id': place['place_id'],
                    'lat': place['geometry']['location']['lat'],
                    'lng': place['geometry']['location']['lng'],
                    'formatted_address': place.get('formatted_address', ''),
                    'rating': place.get('rating'),
                    'user_ratings_total': place.get('user_ratings_total'),
                    'types': place.get('types', [])
                })

            return places
        except Exception as e:
            logger.error(f"Text search error for {query}: {e}")
            return []

    def get_timezone(self, lat: float, lng: float, timestamp: int) -> Optional[Dict[str, Any]]:
        """
        

        Args:
            lat: 
            lng: 
            timestamp: Unix ()

        Returns:
             {timeZoneId, timeZoneName, rawOffset, dstOffset}  None
        """
        try:
            result = self.client.timezone(
                location=(lat, lng),
                timestamp=timestamp
            )

            if result['status'] == 'OK':
                return {
                    'timeZoneId': result['timeZoneId'],
                    'timeZoneName': result['timeZoneName'],
                    'rawOffset': result['rawOffset'],  # 
                    'dstOffset': result['dstOffset']    # 
                }
            return None
        except Exception as e:
            logger.error(f"Timezone error for ({lat}, {lng}): {e}")
            return None

    def get_distance_matrix(
        self,
        origins: List[str],
        destinations: List[str],
        mode: str = "driving",
        departure_time: Optional[str] = None,
        format_output: bool = False
    ) -> Optional[Any]:
        """
        

        Args:
            origins: 
            destinations: 
            mode: 
            departure_time: 
            format_output:
                - False ():  API 
                - True: 

        Returns:
            - format_output=False: {rows: [{elements: [{distance, duration, status}]}], ...}
            - format_output=True: [[{distance, duration, distance_text, duration_text}], ...]
        """
        try:
            kwargs = {
                'origins': origins,
                'destinations': destinations,
                'mode': mode
            }
            if departure_time:
                kwargs['departure_time'] = departure_time

            result = self.client.distance_matrix(**kwargs)

            if result['status'] != 'OK':
                return None

            # 
            if not format_output:
                return result

            # 
            matrix = []
            for row in result['rows']:
                matrix_row = []
                for element in row['elements']:
                    if element['status'] == 'OK':
                        matrix_row.append({
                            'distance': element['distance']['value'],
                            'duration': element['duration']['value'],
                            'distance_text': element['distance']['text'],
                            'duration_text': element['duration']['text']
                        })
                    else:
                        matrix_row.append(None)
                matrix.append(matrix_row)
            return matrix

        except Exception as e:
            logger.error(f"Distance matrix error: {e}")
            return None
