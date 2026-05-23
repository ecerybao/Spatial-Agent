"""
Global Context Database for SpatialAgent

This module provides a global SQLite database for querying pre-indexed
context data from MapEval-Textual.jsonl.

Architecture:
- GlobalContextDB: Singleton SQLite connection with query methods
- ContextManager: Thread-safe manager for global DB

Note:
- , question_id
-  place_name 
-  (origin, destination, mode) 
"""

import sqlite3
import threading
import logging
import unicodedata
import re
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class GlobalContextDB:
    """
     Context ()

     SQLite ,.

    Features:
    - Singleton pattern()
    - Thread-safe( check_same_thread=False)
    - Fuzzy matching()
    - ()
    """

    _instance = None
    _conn = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = "data/local_context.db"):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "data/local_context.db"):
        """
        

        Args:
            db_path: SQLite (: data/local_context.db)

        Note:
            - 
            - 
        """
        if self._conn is not None:
            return  # ,

        self.db_path = Path(db_path)

        if not self.db_path.exists():
            logger.warning(
                f"[GLOBAL_DB] : {db_path}\n"
                f": python data/build_cache.py"
            )
            return

        try:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False  # 
            )
            self._conn.row_factory = sqlite3.Row  # 
            logger.info(f"[GLOBAL_DB] : {db_path}")

            # 
            cursor = self._conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = {'places', 'travel_times', 'routes', 'nearby_places'}
            missing_tables = expected_tables - set(tables)

            if missing_tables:
                logger.error(f"[GLOBAL_DB] : {missing_tables}")
            else:
                logger.debug(f"[GLOBAL_DB] : {tables}")

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            self._conn = None

    def is_connected(self) -> bool:
        """"""
        return self._conn is not None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        ,

        :
        1. : u -> u, a -> a, n -> n
        2. : hostel/hostal -> host, cafe/cafe -> cafe
        3. ,

        Args:
            name: 

        Returns:
            
        """
        if not name:
            return ""

        # 1. Unicode  - 
        # NFD  "a"  "a" + 
        normalized = unicodedata.normalize('NFD', name)

        # 2.  (Combining Diacritical Marks)
        normalized = ''.join(
            char for char in normalized
            if unicodedata.category(char) != 'Mn'
        )

        # 3. 
        normalized = normalized.lower()

        # 4. 
        synonyms = [
            (r'\bhostal\b', 'host'),
            (r'\bhostel\b', 'host'),
            (r'\bhotel\b', 'hotel'),
            (r'\bcafe\b', 'cafe'),
            (r'\bcafe\b', 'cafe'),
            (r'\brestaurante\b', 'restaurant'),
            (r'\brestaurant\b', 'restaurant'),
        ]
        for pattern, replacement in synonyms:
            normalized = re.sub(pattern, replacement, normalized)

        # 5. 
        normalized = ' '.join(normalized.split())

        return normalized

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """
         Levenshtein 

        Args:
            s1: 
            s2: 

        Returns:
            ()
        """
        if len(s1) < len(s2):
            s1, s2 = s2, s1

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # ,,
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _get_all_place_names(self) -> List[Tuple[str, str]]:
        """
        ()

        Returns:
            [(, ), ...]
        """
        if not self.is_connected():
            return []

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT place_name FROM places")
            return [(row[0], self._normalize_name(row[0])) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return []

    def get_place_by_name(self, place_name: str, fuzzy: bool = True) -> Optional[Dict]:
        """
        ()

        :
        1. Level 1: 
        2. Level 2: LIKE 
        3. Level 3: (,)
        4. Level 4: (=2,)

        Args:
            place_name: 
            fuzzy: 

        Returns:
            : {"place_name": "...", "information": "- Location: ...\n- Open: ..."}
             None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()

            # Level 1: 
            cursor.execute("""
                SELECT place_name, information
                FROM places
                WHERE place_name = ?
                LIMIT 1
            """, (place_name,))
            row = cursor.fetchone()

            if row:
                logger.debug(f"[GLOBAL_DB] : '{place_name}'")
                return dict(row)

            if not fuzzy:
                return None

            # Level 2: LIKE 
            cursor.execute("""
                SELECT place_name, information
                FROM places
                WHERE place_name LIKE ?
                LIMIT 1
            """, (f"%{place_name}%",))

            row = cursor.fetchone()
            if row:
                result = dict(row)
                logger.debug(f"[GLOBAL_DB] LIKE : '{place_name}' -> '{result['place_name']}'")
                return result

            # Level 3: 
            query_normalized = self._normalize_name(place_name)
            all_places = self._get_all_place_names()

            for original_name, normalized_name in all_places:
                if query_normalized == normalized_name:
                    cursor.execute("""
                        SELECT place_name, information
                        FROM places
                        WHERE place_name = ?
                        LIMIT 1
                    """, (original_name,))
                    row = cursor.fetchone()
                    if row:
                        result = dict(row)
                        logger.info(f"[GLOBAL_DB] : '{place_name}' -> '{result['place_name']}'")
                        return result

            # Level 4: (,)
            # :  <= 20  <= 2
            if len(place_name) <= 20:
                best_match = None
                best_distance = float('inf')

                for original_name, normalized_name in all_places:
                    distance = self._levenshtein_distance(query_normalized, normalized_name)
                    if distance <= 2 and distance < best_distance:
                        best_distance = distance
                        best_match = original_name

                if best_match:
                    cursor.execute("""
                        SELECT place_name, information
                        FROM places
                        WHERE place_name = ?
                        LIMIT 1
                    """, (best_match,))
                    row = cursor.fetchone()
                    if row:
                        result = dict(row)
                        logger.info(f"[GLOBAL_DB]  (dist={best_distance}): '{place_name}' -> '{result['place_name']}'")
                        return result

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def _get_all_travel_time_keys(self) -> List[Tuple[str, str, str, str, str]]:
        """
        

        Returns:
            [(origin, destination, mode, normalized_origin, normalized_dest), ...]
        """
        if not self.is_connected():
            return []

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT origin, destination, mode FROM travel_times")
            return [
                (row[0], row[1], row[2],
                 self._normalize_name(row[0]), self._normalize_name(row[1]))
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return []

    def get_travel_time(
        self,
        origin: str,
        destination: str,
        mode: str
    ) -> Optional[Dict]:
        """
        ()

        :
        1. Level 1: 
        2. Level 2: LIKE 
        3. Level 3: (,)

        Args:
            origin: 
            destination: 
            mode: (driving, walking, transit, bicycling)

        Returns:
            : {"duration_distance": "Travel Time from A to B by car is 14 mins (3.0 km)."}
             None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()

            # Level 1: 
            cursor.execute("""
                SELECT duration_distance
                FROM travel_times
                WHERE origin = ? AND destination = ? AND mode = ?
                LIMIT 1
            """, (origin, destination, mode))
            row = cursor.fetchone()

            if row:
                logger.debug(f"[GLOBAL_DB] : {origin} -> {destination}")
                return dict(row)

            # Level 2: LIKE ()
            cursor.execute("""
                SELECT duration_distance
                FROM travel_times
                WHERE (origin LIKE ? OR ? LIKE '%' || origin || '%')
                  AND (destination LIKE ? OR ? LIKE '%' || destination || '%')
                  AND mode = ?
                LIMIT 1
            """, (f"%{origin}%", origin, f"%{destination}%", destination, mode))

            row = cursor.fetchone()
            if row:
                logger.debug(f"[GLOBAL_DB] LIKE : {origin} -> {destination}")
                return dict(row)

            # Level 2b: ()
            # ,
            origin_keywords = set(w.lower() for w in re.split(r'[,\s]+', origin) if len(w) > 2)
            dest_keywords = set(w.lower() for w in re.split(r'[,\s]+', destination) if len(w) > 2)

            cursor.execute("SELECT DISTINCT origin, destination FROM travel_times WHERE mode = ?", (mode,))
            for db_origin, db_dest in cursor.fetchall():
                db_origin_kw = set(w.lower() for w in re.split(r'[,\s]+', db_origin) if len(w) > 2)
                db_dest_kw = set(w.lower() for w in re.split(r'[,\s]+', db_dest) if len(w) > 2)

                # (2)
                origin_match = len(origin_keywords & db_origin_kw) >= min(2, len(origin_keywords))
                dest_match = len(dest_keywords & db_dest_kw) >= min(2, len(dest_keywords))

                if origin_match and dest_match:
                    cursor.execute("""
                        SELECT duration_distance
                        FROM travel_times
                        WHERE origin = ? AND destination = ? AND mode = ?
                        LIMIT 1
                    """, (db_origin, db_dest, mode))
                    row = cursor.fetchone()
                    if row:
                        logger.info(f"[GLOBAL_DB] : '{origin}' -> '{destination}' (: '{db_origin}' -> '{db_dest}')")
                        return dict(row)

            # Level 3: 
            origin_normalized = self._normalize_name(origin)
            dest_normalized = self._normalize_name(destination)
            all_keys = self._get_all_travel_time_keys()

            for orig, dest, m, orig_norm, dest_norm in all_keys:
                if m == mode and orig_norm == origin_normalized and dest_norm == dest_normalized:
                    cursor.execute("""
                        SELECT duration_distance
                        FROM travel_times
                        WHERE origin = ? AND destination = ? AND mode = ?
                        LIMIT 1
                    """, (orig, dest, mode))
                    row = cursor.fetchone()
                    if row:
                        logger.info(f"[GLOBAL_DB] : '{origin}' -> '{dest}' (mode={mode})")
                        return dict(row)

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def _get_all_route_keys(self) -> List[Tuple[str, str, str, str, str]]:
        """
        

        Returns:
            [(origin, destination, mode, normalized_origin, normalized_dest), ...]
        """
        if not self.is_connected():
            return []

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT origin, destination, mode FROM routes")
            return [
                (row[0], row[1], row[2],
                 self._normalize_name(row[0]), self._normalize_name(row[1]))
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return []

    def get_routes(
        self,
        origin: str,
        destination: str,
        mode: str
    ) -> Optional[Dict]:
        """
        ()

        :
        1. Level 1: 
        2. Level 2: LIKE 
        3. Level 3: (,)

        Args:
            origin: 
            destination: 
            mode: 

        Returns:
            : {"summary": "1. Via I-70 E | 11 mins | 4.8 mi\n2. Via E Whittier St | 12 mins | 4.1 mi\n..."}
             None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()

            # Level 1: 
            cursor.execute("""
                SELECT summary
                FROM routes
                WHERE origin = ? AND destination = ? AND mode = ?
                LIMIT 1
            """, (origin, destination, mode))
            row = cursor.fetchone()

            if row:
                logger.debug(f"[GLOBAL_DB] : {origin} -> {destination}")
                return dict(row)

            # Level 2: LIKE 
            cursor.execute("""
                SELECT summary
                FROM routes
                WHERE (origin LIKE ? OR ? LIKE '%' || origin || '%')
                  AND (destination LIKE ? OR ? LIKE '%' || destination || '%')
                  AND mode = ?
                LIMIT 1
            """, (f"%{origin}%", origin, f"%{destination}%", destination, mode))

            row = cursor.fetchone()
            if row:
                logger.debug(f"[GLOBAL_DB] LIKE : {origin} -> {destination}")
                return dict(row)

            # Level 3: 
            origin_normalized = self._normalize_name(origin)
            dest_normalized = self._normalize_name(destination)
            all_keys = self._get_all_route_keys()

            for orig, dest, m, orig_norm, dest_norm in all_keys:
                if m == mode and orig_norm == origin_normalized and dest_norm == dest_normalized:
                    cursor.execute("""
                        SELECT summary
                        FROM routes
                        WHERE origin = ? AND destination = ? AND mode = ?
                        LIMIT 1
                    """, (orig, dest, mode))
                    row = cursor.fetchone()
                    if row:
                        logger.info(f"[GLOBAL_DB] : '{origin}' -> '{dest}' (mode={mode})")
                        return dict(row)

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def get_all_places(self) -> List[Dict]:
        """
        

        Returns:
            : [{"place_name": "...", "information": "..."}, ...]
        """
        if not self.is_connected():
            return []

        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT place_name, information FROM places")

            results = []
            for row in cursor.fetchall():
                results.append(dict(row))

            return results

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return []

    def get_stats(self) -> Dict:
        """
        

        Returns:
            : {"places": 500, "travel_times": 300, "routes": 200, "nearby_places": 100}
        """
        if not self.is_connected():
            return {}

        try:
            cursor = self._conn.cursor()

            stats = {}
            for table in ['places', 'travel_times', 'routes', 'nearby_places']:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]

            #  places
            cursor.execute("SELECT COUNT(*) FROM places WHERE lat IS NOT NULL")
            stats['places_with_coords'] = cursor.fetchone()[0]

            return stats

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return {}

    def get_place_coordinates(self, place_name: str, fuzzy: bool = True) -> Optional[Tuple[float, float]]:
        """
        

        Args:
            place_name: 
            fuzzy: 

        Returns:
            (lat, lng) , None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()

            # Level 1: 
            cursor.execute("""
                SELECT lat, lng FROM places
                WHERE place_name = ? AND lat IS NOT NULL
                LIMIT 1
            """, (place_name,))
            row = cursor.fetchone()

            if row:
                logger.debug(f"[GLOBAL_DB] : '{place_name}'")
                return (row['lat'], row['lng'])

            if not fuzzy:
                return None

            # Level 2: LIKE 
            cursor.execute("""
                SELECT lat, lng FROM places
                WHERE place_name LIKE ? AND lat IS NOT NULL
                LIMIT 1
            """, (f"%{place_name}%",))
            row = cursor.fetchone()

            if row:
                logger.debug(f"[GLOBAL_DB] LIKE : '{place_name}'")
                return (row['lat'], row['lng'])

            # Level 3: 
            query_normalized = self._normalize_name(place_name)
            all_places = self._get_all_place_names()

            for original_name, normalized_name in all_places:
                if query_normalized == normalized_name:
                    cursor.execute("""
                        SELECT lat, lng FROM places
                        WHERE place_name = ? AND lat IS NOT NULL
                        LIMIT 1
                    """, (original_name,))
                    row = cursor.fetchone()
                    if row:
                        logger.info(f"[GLOBAL_DB] : '{place_name}' -> '{original_name}'")
                        return (row['lat'], row['lng'])

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def _normalize_category(self, category: str) -> str:
        """
         category (,)

        Examples:
            "Laundry" -> "laundr"
            "Laundries" -> "laundr"
            "mosque" -> "mosqu"
            "Mosques" -> "mosqu"
        """
        if not category:
            return ""
        # 
        norm = category.lower().strip()
        # 
        for suffix in ['ies', 'es', 'y', 's']:
            if norm.endswith(suffix) and len(norm) > len(suffix) + 2:
                norm = norm[:-len(suffix)]
                break
        return norm

    def _category_matches(self, query_cat: str, db_cat: str) -> bool:
        """
         category ()

        :
        1. ()
        2. ()
        3. 
        4. 
        """
        if not query_cat or not db_cat:
            return True

        q_lower = query_cat.lower().strip()
        d_lower = db_cat.lower().strip()

        # 
        if q_lower == d_lower:
            return True

        # 
        if self._normalize_category(query_cat) == self._normalize_category(db_cat):
            return True

        # ( "Gallery, Museum" vs "museum" )
        # (hindu_temple -> hindu temple)
        q_normalized = query_cat.replace('_', ' ').replace(',', ' ').lower()
        d_normalized = db_cat.replace('_', ' ').replace(',', ' ').lower()

        # 
        if q_normalized == d_normalized:
            return True

        # 
        q_parts = [p.strip() for p in q_normalized.split() if p.strip()]
        for part in q_parts:
            if part in d_normalized or d_normalized in part:
                return True

        # 
        synonyms = [
            ({'dental', 'dentist', 'dentists', 'dental clinics', 'dental clinic'}),
            ({'hospital', 'hospitals', 'medical', 'clinic', 'clinics'}),
            ({'restaurant', 'restaurants', 'food', 'dining'}),
            ({'museum', 'museums', 'gallery', 'galleries'}),
            ({'temple', 'temples', 'hindu temple', 'hindu temples'}),
            ({'mosque', 'mosques', 'masjid'}),
            ({'park', 'parks', 'garden', 'gardens'}),
            ({'cafe', 'cafes', 'cafe', 'cafes', 'coffee', 'coffee shop'}),
            ({'tourist attraction', 'tourist attractions', 'attraction', 'attractions'}),
            ({'post office', 'post offices'}),
            ({'movie theater', 'movie theaters', 'cinema', 'cinemas'}),
        ]
        for syn_group in synonyms:
            q_match = any(s in q_lower for s in syn_group)
            d_match = any(s in d_lower for s in syn_group)
            if q_match and d_match:
                return True

        return False

    def _name_matches(self, query_name: str, db_name: str) -> bool:
        """
        ()

        :
        1. 
        2. 
        3. ()
        4. ()
        """
        if not query_name or not db_name:
            return False

        q_lower = query_name.lower().strip()
        d_lower = db_name.lower().strip()

        # 
        if q_lower == d_lower:
            return True

        # 
        if q_lower in d_lower or d_lower in q_lower:
            return True

        # 
        spelling_variants = [
            ('comilla', 'cumilla'),  # ID 135
            ('agargaon ict tower', 'ict tower'),  # ID 34
        ]
        for v1, v2 in spelling_variants:
            if (v1 in q_lower and v2 in d_lower) or (v2 in q_lower and v1 in d_lower):
                return True

        # : SUST -> Shahjalal University of Science and Technology
        #  query , db_name 
        if len(q_lower) <= 10 and len(d_lower) > 20:
            words = d_lower.split()
            if len(words) >= 2:
                # (of, and, the, for, in, at )
                stop_words = {'of', 'and', 'the', 'for', 'in', 'at', 'to', 'a', 'an'}
                significant_words = [w for w in words if w not in stop_words and w and w[0].isalpha()]
                # 
                acronym = ''.join(w[0] for w in significant_words)
                if q_lower == acronym:
                    return True

        # : "Sacre-Cur Basilica" vs "Basilique du Sacre-Cur de Montmartre"
        # ()
        import re
        stop_words = {'of', 'and', 'the', 'for', 'in', 'at', 'to', 'a', 'an', 'de', 'du', 'la', 'le', 'les'}

        def extract_keywords(text):
            # 
            words = re.split(r'[\s\-,./]+', text.lower())
            return {w for w in words if len(w) >= 3 and w not in stop_words}

        q_keywords = extract_keywords(query_name)
        d_keywords = extract_keywords(db_name)

        if q_keywords and d_keywords:
            # ,
            overlap = len(q_keywords & d_keywords)
            min_len = min(len(q_keywords), len(d_keywords))
            if min_len > 0 and overlap / min_len >= 0.5:
                return True

        return False

    def get_nearby_places(self, reference_place: str, category: str = None) -> Optional[List[Dict]]:
        """
        ()

        Args:
            reference_place:  (e.g., "Tower of London")
            category: , (Parks, Restaurants, etc.)

        Returns:
            , rank, name, address, rating, rating_count, opening_hours, price_level
             None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()
            row = None
            matched_ref_name = reference_place  #  reference_place 

            if category:
                # Level 1:  reference_place  category
                cursor.execute("""
                    SELECT nearby_text FROM nearby_places
                    WHERE reference_place = ? AND category = ?
                """, (reference_place, category))
                row = cursor.fetchone()

                # Level 2: LIKE  reference_place, category
                if not row:
                    cursor.execute("""
                        SELECT reference_place, nearby_text FROM nearby_places
                        WHERE reference_place LIKE ? AND category = ?
                    """, (f"%{reference_place}%", category))
                    row = cursor.fetchone()
                    if row:
                        matched_ref_name = row['reference_place']

                # Level 3:  category(,)
                #  :, reference_place,
                if not row:
                    cursor.execute("""
                        SELECT reference_place, category, nearby_text FROM nearby_places
                    """)
                    all_rows = cursor.fetchall()

                    # : >  > 
                    exact_matches = []      # reference_place ()
                    substring_matches = []  # reference_place 
                    fuzzy_matches = []      # _name_matches 

                    for r in all_rows:
                        db_ref, db_cat, db_text = r['reference_place'], r['category'], r['nearby_text']

                        #  category 
                        cat_match = self._category_matches(category, db_cat)
                        if not cat_match:
                            continue

                        #  reference_place 
                        ref_lower = reference_place.lower()
                        db_ref_lower = db_ref.lower()

                        if ref_lower == db_ref_lower:
                            # ()
                            exact_matches.append((db_ref, db_text))
                        elif ref_lower in db_ref_lower or db_ref_lower in ref_lower:
                            # ()
                            substring_matches.append((db_ref, db_text))
                        elif self._name_matches(reference_place, db_ref):
                            # ()
                            fuzzy_matches.append((db_ref, db_text))

                    # 
                    best_match = None
                    if exact_matches:
                        best_match = exact_matches[0]
                        logger.debug(f"[GLOBAL_DB] : '{reference_place}' -> '{best_match[0]}'")
                    elif substring_matches:
                        # : query  db_ref ()
                        #  "St. Lawrence Market"  "St. Lawrence Market"  "Khansa market"
                        for db_ref, db_text in substring_matches:
                            if reference_place.lower() in db_ref.lower():
                                best_match = (db_ref, db_text)
                                break
                        if not best_match:
                            best_match = substring_matches[0]
                        logger.debug(f"[GLOBAL_DB] : '{reference_place}' -> '{best_match[0]}'")
                    elif fuzzy_matches:
                        best_match = fuzzy_matches[0]
                        logger.debug(f"[GLOBAL_DB] : '{reference_place}' -> '{best_match[0]}'")

                    if best_match:
                        row = {'nearby_text': best_match[1]}
                        matched_ref_name = best_match[0]
            else:
                #  category,
                cursor.execute("""
                    SELECT reference_place, nearby_text FROM nearby_places
                    WHERE reference_place = ?
                    LIMIT 1
                """, (reference_place,))
                row = cursor.fetchone()
                if row:
                    matched_ref_name = row['reference_place']

                if not row:
                    cursor.execute("""
                        SELECT reference_place, nearby_text FROM nearby_places
                        WHERE reference_place LIKE ?
                        LIMIT 1
                    """, (f"%{reference_place}%",))
                    row = cursor.fetchone()
                    if row:
                        matched_ref_name = row['reference_place']

            if row:
                nearby_text = row['nearby_text'] if row['nearby_text'] else ''
                # 
                places = self._parse_nearby_text(nearby_text)

                #  places  rating/price_level/opening_hours 
                places = self._enrich_nearby_places_with_details(places)

                #  7: reference_place 
                #  matched_ref_name()
                places = self._calculate_distances_and_rerank(places, matched_ref_name)

                logger.debug(f"[GLOBAL_DB]  {len(places)} : {reference_place} (DB: {matched_ref_name})")
                return places

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def _parse_nearby_text(self, text: str) -> List[Dict]:
        """
         nearby_text 

        Args:
            text: ,:
                Nearby Restaurants of St. Lawrence Market are (...):
                1. <b>A&W Canada</b>
                - Address: 85 Front St E, ...
                - Rating: 3.9. (339 ratings).
                - Price Level: Inexpensive.
                - Open: Monday: Open 24 hours, ...

        Returns:
            [{"rank": 1, "name": "A&W Canada", "address": "...", "rating": 3.9, ...}, ...]
        """
        import re
        places = []

        # 1: "1. <b>Name</b>"  "1. <b>Name</b>(lat, lng)"
        entry_pattern = r'(\d+)\.\s*<b>([^<]+)</b>(?:\((-?\d+\.?\d*),\s*(-?\d+\.?\d*)\))?'

        for entry_match in re.finditer(entry_pattern, text):
            rank = int(entry_match.group(1))
            name = entry_match.group(2).strip()

            # ()
            lat = float(entry_match.group(3)) if entry_match.group(3) else None
            lng = float(entry_match.group(4)) if entry_match.group(4) else None

            # ()
            entry_end = entry_match.end()
            next_entry = re.search(r'\d+\.\s*<b>', text[entry_end:])
            if next_entry:
                details_end = entry_end + next_entry.start()
            else:
                details_end = len(text)

            details = text[entry_end:details_end]

            place_info = {"rank": rank, "name": name}

            # ()
            if lat is not None and lng is not None:
                place_info["lat"] = lat
                place_info["lng"] = lng

            # 
            addr_match = re.search(r'-\s*Address:\s*(.+?)(?=\n-|\n\d+\.|$)', details, re.DOTALL)
            if addr_match:
                place_info["address"] = addr_match.group(1).strip().rstrip('.')

            # 
            rating_match = re.search(r'-\s*Rating:\s*(\d+\.?\d*)\.\s*\((\d+)\s*ratings?\)', details)
            if rating_match:
                place_info["rating"] = float(rating_match.group(1))
                place_info["rating_count"] = int(rating_match.group(2))

            # 
            price_match = re.search(r'-\s*Price Level:\s*(\w+)', details)
            if price_match:
                place_info["price_level"] = price_match.group(1).strip()

            # 
            open_match = re.search(r'-\s*Open:\s*(.+?)(?=\n-|\n\d+\.|$)', details, re.DOTALL)
            if open_match:
                place_info["opening_hours"] = open_match.group(1).strip()

            places.append(place_info)

        # 2: "1. Name | Address" ( <b> , | )
        # : "1. AIA New York | Center for Architecture | 536 LaGuardia Place, New York"
        if not places:
            #  | 
            pipe_pattern = r'(\d+)\.\s*([^|\n]+?)(?:\s*\|\s*([^|\n]+?))?(?:\s*\|\s*([^\n]+))?(?:\n|$)'
            for entry_match in re.finditer(pipe_pattern, text):
                rank = int(entry_match.group(1))
                # ,
                parts = [entry_match.group(2)]
                if entry_match.group(3):
                    parts.append(entry_match.group(3))
                if entry_match.group(4):
                    parts.append(entry_match.group(4))

                # ,
                name = parts[0].strip() if parts else ""
                address = parts[-1].strip() if len(parts) > 1 else ""

                if name:
                    place_info = {"rank": rank, "name": name}
                    if address:
                        place_info["address"] = address
                    places.append(place_info)

        #  rank 
        places.sort(key=lambda x: x["rank"])
        return places

    def _enrich_nearby_places_with_details(self, places: List[Dict]) -> List[Dict]:
        """
         places  nearby (rating, price_level, opening_hours)

        :MapEval-Textual.jsonl  Nearby , Information .
         nearby_places  places ,.
        """
        import re

        if not places:
            return places

        for place in places:
            place_name = place.get('name')
            if not place_name:
                continue

            #  rating ,( nearby_text )
            if place.get('rating') is not None:
                continue

            #  get_place_by_name ()
            place_info = self.get_place_by_name(place_name, fuzzy=True)
            if place_info and place_info.get('information'):
                info_text = place_info['information']

                #  rating: "Rating: 4.6. (2256 ratings)."
                rating_match = re.search(r'Rating:\s*(\d+\.?\d*)\.\s*\((\d+)\s*ratings?\)', info_text)
                if rating_match:
                    place['rating'] = float(rating_match.group(1))
                    place['rating_count'] = int(rating_match.group(2))

                #  price_level: "Price Level: Moderate."
                price_match = re.search(r'Price Level:\s*(\w+)', info_text)
                if price_match:
                    place['price_level'] = price_match.group(1)

                #  opening_hours: "Open: Monday: ..."
                if not place.get('opening_hours'):
                    open_match = re.search(r'Open:\s*(.+?)(?:\n-|\n\n|$)', info_text, re.DOTALL)
                    if open_match:
                        place['opening_hours'] = open_match.group(1).strip()

        return places

    def _calculate_distances_and_rerank(self, places: List[Dict], reference_place: str) -> List[Dict]:
        """
         nearby  reference_place ,

         7:MapEval  nearby places .
         Haversine ,, evaluator 
        "nearest" .

        Args:
            places: , lat/lng 
            reference_place: 

        Returns:
            , distance_meters 
        """
        import math

        if not places:
            return places

        # 1.  reference_place 
        ref_coords = self._get_place_coordinates(reference_place)
        if not ref_coords:
            logger.debug(f"[GLOBAL_DB] : {reference_place},")
            return places

        ref_lat, ref_lng = ref_coords

        # 2. 
        for place in places:
            place_lat = place.get('lat')
            place_lng = place.get('lng')

            if place_lat is not None and place_lng is not None:
                distance = self._haversine_distance(ref_lat, ref_lng, place_lat, place_lng)
                place['distance_meters'] = round(distance, 1)
            else:
                # ,,
                place['distance_meters'] = float('inf')

        # 3. 
        places.sort(key=lambda x: x.get('distance_meters', float('inf')))

        # 4.  rank 
        for i, place in enumerate(places, 1):
            place['rank'] = i

        # 
        places_with_distance = [p for p in places if p.get('distance_meters') != float('inf')]
        if places_with_distance:
            logger.debug(f"[GLOBAL_DB]  {len(places_with_distance)} ")
            # 3
            for p in places_with_distance[:3]:
                logger.debug(f"  Rank {p['rank']}: {p['name']} - {p.get('distance_meters', '?')}m")

        return places

    def _get_place_coordinates(self, place_name: str) -> Optional[Tuple[float, float]]:
        """
         places 

        Args:
            place_name: 

        Returns:
            (lat, lng) , None
        """
        if not self.is_connected():
            return None

        try:
            cursor = self._conn.cursor()

            # 
            cursor.execute("""
                SELECT lat, lng FROM places WHERE place_name = ? AND lat IS NOT NULL
            """, (place_name,))
            row = cursor.fetchone()

            if not row:
                # 
                cursor.execute("""
                    SELECT lat, lng FROM places WHERE place_name LIKE ? AND lat IS NOT NULL
                """, (f"%{place_name}%",))
                row = cursor.fetchone()

            if row and row['lat'] is not None and row['lng'] is not None:
                return (row['lat'], row['lng'])

            return None

        except Exception as e:
            logger.error(f"[GLOBAL_DB] : {e}")
            return None

    def _haversine_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
         Haversine ()

        Args:
            lat1, lng1: 
            lat2, lng2: 

        Returns:
            ()
        """
        import math

        R = 6371000  # ()

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def get_nearest_place(self, reference_place: str, category: str = None) -> Optional[Dict]:
        """
        (rank = 1)

        Args:
            reference_place: 
            category: ,

        Returns:
            , None
        """
        places = self.get_nearby_places(reference_place, category)
        if places and len(places) > 0:
            return places[0]  # 
        return None


class ContextManager:
    """
    (,)

    :
    -  GlobalContextDB 
    - 
    -  intent, trip/routing 

    Usage:
        # (SpatialAgent.__init__)
        ContextManager.initialize_db("data/context_cache.db")

        #  intent( execute )
        ContextManager.set_current_intent("routing")

        #  operator ( intent)
        if ContextManager.should_use_local_db():
            db = ContextManager.get_db()
            routes = db.get_routes("A", "B", "driving")

        # 
        ContextManager.close_db()
    """

    _global_db: Optional[GlobalContextDB] = None
    _current_intent: Optional[str] = None  #  intent
    _allowed_intents = {'trip', 'routing', 'poi', 'nearby'}  #  intent
    _lock = threading.Lock()

    @classmethod
    def initialize_db(cls, db_path: str = "data/context_cache.db"):
        """
        ()

        Args:
            db_path: SQLite 
        """
        with cls._lock:
            if cls._global_db is None:
                cls._global_db = GlobalContextDB(db_path)

                if cls._global_db.is_connected():
                    stats = cls._global_db.get_stats()
                    logger.info(f"[CONTEXT_MANAGER] ")
                    logger.info(f"[CONTEXT_MANAGER] : {stats}")
                else:
                    logger.warning("[CONTEXT_MANAGER] , Google Maps API")
                    cls._global_db = None

    @classmethod
    def get_db(cls) -> Optional[GlobalContextDB]:
        """
        

        Returns:
            GlobalContextDB , None
        """
        if cls._global_db is None:
            # ()
            cls.initialize_db()

        return cls._global_db

    @classmethod
    def set_current_intent(cls, intent: str):
        """
         intent( execute )

        Args:
            intent:  intent (nearby/routing/trip/poi)
        """
        cls._current_intent = intent
        logger.debug(f"[CONTEXT_MANAGER]  intent: {intent}")

    @classmethod
    def get_current_intent(cls) -> Optional[str]:
        """ intent"""
        return cls._current_intent

    @classmethod
    def should_use_local_db(cls) -> bool:
        """
         intent 

        Returns:
            True  intent  trip  routing, False
        """
        if cls._current_intent is None:
            logger.debug("[CONTEXT_MANAGER]  intent,")
            return False

        allowed = cls._current_intent in cls._allowed_intents
        if not allowed:
            logger.debug(f"[CONTEXT_MANAGER] intent '{cls._current_intent}' ,")
        return allowed

    @classmethod
    def clear_current_intent(cls):
        """ intent( execute )"""
        cls._current_intent = None

    @classmethod
    def close_db(cls):
        """
        

        Note:
            - 
            - 
        """
        with cls._lock:
            if cls._global_db and cls._global_db._conn:
                cls._global_db._conn.close()
                logger.info("[CONTEXT_MANAGER] ")
                cls._global_db = None
