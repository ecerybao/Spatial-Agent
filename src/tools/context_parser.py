"""
Context Parser for MapEval-Textual.jsonl

This module parses the 'context' field from MapEval-Textual.jsonl,
extracting places, travel times, and routes information.
"""

import re
from typing import Dict, Tuple, List, Optional


class ContextParser:
    """ MapEval-Textual context """

    @staticmethod
    def _clean_html_tags(text: str) -> str:
        """ HTML """
        #  HTML 
        text = re.sub(r'<[^>]+>', '', text)
        # 
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def parse_places(context: str) -> Dict[str, str]:
        """
        

        :
            Information of <b>Hostal El Grial</b>:
            - Location: Calle Carmen Alto 112, San Blas, Cusco 08003, Peru.
            - Open: Monday: 7:00 AM - 5:30 PM, ...

        Args:
            context: MapEval-Textual  context 

        Returns:
            {
                "Hostal El Grial": "- Location: Calle Carmen Alto 112...\n- Open: Monday: 7:00 AM...",
                "Saqsaywaman": "- Location: Cusco 08002, Peru.\n- Open: Monday: 7:00 AM..."
            }
        """
        places = {}

        # : Information of 
        pattern = r'Information of <b>(.*?)</b>:(.*?)(?=Information of <b>|Travel Time|Nearby|There are \d+ routes|Current location|$)'

        for match in re.finditer(pattern, context, re.DOTALL):
            place_name = match.group(1).strip()
            info_block = match.group(2).strip()

            #  HTML 
            place_name = ContextParser._clean_html_tags(place_name)
            info_block = ContextParser._clean_html_tags(info_block)

            places[place_name] = info_block

        return places

    @staticmethod
    def parse_travel_times(context: str) -> Dict[Tuple[str, str, str], str]:
        """
        ()

        :
            1: Travel Time from Hostal El Grial to Saqsaywaman by car is 14 mins (3.0 km).
            2: Distance from Oakwood Premier Melbourne to Marvel Stadium is 1.9 km (6 mins) by car.
            3: Distance from Indira Road to Multiplan Center by public transport is 3.6 km (12 mins).

        Args:
            context: MapEval-Textual  context 

        Returns:
            {
                ("Hostal El Grial", "Saqsaywaman", "driving"): "Travel Time from ... is 14 mins (3.0 km).",
                ("Oakwood Premier Melbourne", "Marvel Stadium", "driving"): "Distance from ... is 1.9 km (6 mins) by car."
            }
        """
        travel_times = {}

        mode_map = {
            "by car": "driving",
            "on foot": "walking",
            "by public transport": "transit",
            "by cycle": "bicycling"
        }

        # 1: Travel Time from A to B by car is X mins (Y km).
        pattern1 = r'(Travel Time from .*? to .*? (?:by car|on foot|by public transport|by cycle) is .*? \(.*?\)\.)'

        # 2: Distance from A to B is X km (Y mins) by car.
        # 3: Distance from A to B by public transport is X km (Y mins).
        pattern2 = r'(Distance from .+? to .+? (?:by car|on foot|by public transport|by cycle )?is \d+\.?\d* km \(\d+ mins?\).*?\.)'

        for match in re.finditer(pattern1, context):
            sentence = match.group(1).strip()
            detail_pattern = r'Travel Time from (.*?) to (.*?) (by car|on foot|by public transport|by cycle) is'
            detail_match = re.search(detail_pattern, sentence)

            if detail_match:
                origin = detail_match.group(1).strip()
                dest = detail_match.group(2).strip()
                mode_text = detail_match.group(3).strip()
                mode = mode_map.get(mode_text, "driving")

                origin = ContextParser._clean_html_tags(origin)
                dest = ContextParser._clean_html_tags(dest)
                sentence_clean = ContextParser._clean_html_tags(sentence)

                travel_times[(origin, dest, mode)] = sentence_clean

        #  Distance from 
        for match in re.finditer(pattern2, context):
            sentence = match.group(1).strip()

            # : Distance from A to B by public transport is X km (Y mins).
            detail_pattern1 = r'Distance from (.+?) to (.+?) (by car|on foot|by public transport|by cycle) is'
            # : Distance from A to B is X km (Y mins) by car.
            detail_pattern2 = r'Distance from (.+?) to (.+?) is \d+\.?\d* km \(\d+ mins?\) (by car|on foot|by public transport|by cycle)'
            # : Distance from A to B is X km (Y mins). ( driving)
            detail_pattern3 = r'Distance from (.+?) to (.+?) is \d+\.?\d* km \(\d+ mins?\)\.'

            detail_match = re.search(detail_pattern1, sentence)
            if not detail_match:
                detail_match = re.search(detail_pattern2, sentence)

            if detail_match:
                origin = detail_match.group(1).strip()
                dest = detail_match.group(2).strip()
                mode_text = detail_match.group(3).strip()
                mode = mode_map.get(mode_text, "driving")
            else:
                #  mode 
                detail_match = re.search(detail_pattern3, sentence)
                if detail_match:
                    origin = detail_match.group(1).strip()
                    dest = detail_match.group(2).strip()
                    mode = "driving"  # 
                else:
                    continue

            origin = ContextParser._clean_html_tags(origin)
            dest = ContextParser._clean_html_tags(dest)
            sentence_clean = ContextParser._clean_html_tags(sentence)

            travel_times[(origin, dest, mode)] = sentence_clean

        return travel_times

    @staticmethod
    def parse_routes(context: str) -> Dict[Tuple[str, str, str], str]:
        """
        

        :
            There are 3 routes from South Wind Motel to Brassica in Bexley by car. They are:
            1. Via I-70 E | 11 mins | 4.8 mi
            - Head north on US-23 N/S High St toward Shumacher Alley
            2. Via E Whittier St | 12 mins | 4.1 mi

        Args:
            context: MapEval-Textual  context 

        Returns:
            {
                ("South Wind Motel", "Brassica in Bexley", "driving"): "1. Via I-70 E | 11 mins | 4.8 mi\n- Head north...\n2. Via E Whittier St | 12 mins | 4.1 mi"
            }
        """
        routes = {}

        # : mode(3)
        pattern = r'There are \d+ routes from (.*?) to (.*?) (on foot|by car|by cycle|by public transport)\. They are:(.*?)(?=There are \d+ routes|Current location|$)'

        mode_map = {
            "on foot": "walking",
            "by car": "driving",
            "by cycle": "bicycling",
            "by public transport": "transit"
        }

        for match in re.finditer(pattern, context, re.DOTALL):
            origin = match.group(1).strip()
            dest = match.group(2).strip()
            mode_text = match.group(3).strip()  #  mode
            routes_text = match.group(4).strip()

            mode = mode_map.get(mode_text, "driving")

            #  HTML 
            origin_clean = ContextParser._clean_html_tags(origin)
            dest_clean = ContextParser._clean_html_tags(dest)
            routes_text_clean = ContextParser._clean_html_tags(routes_text)

            routes[(origin_clean, dest_clean, mode)] = routes_text_clean

        return routes

    @staticmethod
    def parse_place_coordinates(context: str) -> Dict[str, Tuple[float, float]]:
        """
        

        :
            Information of <b>Athens</b>:
            - Location: Athens, Greece(37.9838, 23.7275).

            <b>Potters Fields Park</b>(51.5041, -0.0783)

        Args:
            context: MapEval-Textual  context 

        Returns:
            {"Athens": (37.9838, 23.7275), "Potters Fields Park": (51.5041, -0.0783)}
        """
        coords = {}

        # 1: Location  - "Location: Athens, Greece(37.9838, 23.7275)."
        #  Information of <b>name</b>, info 
        info_pattern = r'Information of <b>([^<]+)</b>:[^(]*?Location:[^(]*?\((-?\d+\.?\d*),\s*(-?\d+\.?\d*)\)'
        for match in re.finditer(info_pattern, context, re.DOTALL):
            name = match.group(1).strip()
            lat = float(match.group(2))
            lng = float(match.group(3))
            coords[name] = (lat, lng)

        # 2:  - "<b>Potters Fields Park</b>(51.5041, -0.0783)"
        name_coord_pattern = r'<b>([^<]+)</b>\((-?\d+\.?\d*),\s*(-?\d+\.?\d*)\)'
        for match in re.finditer(name_coord_pattern, context):
            name = match.group(1).strip()
            lat = float(match.group(2))
            lng = float(match.group(3))
            # (Information of )
            if name not in coords:
                coords[name] = (lat, lng)

        return coords

    @staticmethod
    def parse_nearby_places(context: str) -> List[Dict]:
        """
         Nearby  - 

        :
            Information of <b>St. Lawrence Market</b>:
            - Location: Toronto, ON M5E 1C3, Canada.

            Nearby Restaurants of St. Lawrence Market are (sorted by distance in ascending order):
            1. <b>A&W Canada</b>
            - Address: 85 Front St E, Toronto, ON M5E 1B8, Canada.
            - Rating: 3.9. (339 ratings).
            - Price Level: Inexpensive.
            - Open: Monday: Open 24 hours, ...
            2. <b>Yianni's Kitchen</b>
            ...

        Returns:
            [
                {
                    "reference_place": "St. Lawrence Market",
                    "reference_info": "Location: Toronto, ON M5E 1C3, Canada.",
                    "category": "Restaurants",
                    "radius_meters": None,
                    "nearby_text": "1. <b>A&W Canada</b>\n- Address: ...\n2. <b>Yianni's Kitchen</b>\n..."
                }
            ]
        """
        results = []

        #  Information 
        places_info = ContextParser.parse_places(context)

        #  Nearby header
        # 1: "Nearby Parks of Tower of London are (in 1000 m radius):"
        # 2: "Nearby Restaurants of Khansa market are (sorted by distance in ascending order):"
        # 3: "Nearby places of Washington Square Park of type "museum" are (...)"
        # 4: "Nearby Post Offices of Mymensingh are (...)" - 
        # 5: "Nearby Tourist Attractions of XXX are (...)" - 
        # : [\w\s]+ ( Post Offices, Movie Theaters, Tourist Attractions)
        header_pattern = r'Nearby ([\w\s]+?) of (.+?)(?:\s+of type\s+"([^"]+)")?\s+are \(([^)]+)\):'

        for header_match in re.finditer(header_pattern, context):
            category_word = header_match.group(1).strip()  # "places"  "Restaurants"
            reference_place = header_match.group(2).strip()  # 
            type_category = header_match.group(3)  # of type "xxx" , None
            sort_info = header_match.group(4).strip()  # /

            #  category
            if type_category:
                category = type_category  #  of type "xxx" 
            else:
                category = category_word  #  Nearby 

            #  radius()
            radius_meters = None
            radius_match = re.search(r'in\s+(\d+)\s*m\s+radius', sort_info)
            if radius_match:
                radius_meters = int(radius_match.group(1))

            #  reference_place  Information
            reference_info = places_info.get(reference_place, '')

            #  header , section
            header_start = header_match.start()
            header_end = header_match.end()

            #  section (Nearby, Information, Travel Time, routes )
            next_section_pattern = r'\n(?:Nearby \w+ of|Information of|Travel Time|There are \d+ routes|Current location)'
            next_section = re.search(next_section_pattern, context[header_end:])
            if next_section:
                block_end = header_end + next_section.start()
            else:
                block_end = len(context)

            # ( header)
            nearby_text = context[header_start:block_end].strip()

            result = {
                "reference_place": reference_place,
                "reference_info": reference_info,
                "category": category,
                "nearby_text": nearby_text
            }
            if radius_meters is not None:
                result["radius_meters"] = radius_meters

            results.append(result)

        return results
