from typing import List, Dict, Any
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import datetime
import math


# ====================  ====================

def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
     Haversine ()

    Args:
        lat1, lng1: 
        lat2, lng2: 

    Returns:
        ()
    """
    R = 6371000  # ()

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = math.sin(delta_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    12(,0-360,0=)

    Args:
        lat1, lng1: 
        lat2, lng2: 

    Returns:
        ()
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lng2 - lng1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - \
        math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)

    theta = math.atan2(y, x)
    bearing_deg = (math.degrees(theta) + 360) % 360

    return bearing_deg


def bearing_to_direction(bearing_deg: float, num_directions: int = 8) -> str:
    """
    

    Args:
        bearing_deg: (0-360)
        num_directions: , 4  8
            - 4: N, E, S, W
            - 8: N, NE, E, SE, S, SW, W, NW

    Returns:
        
    """
    if num_directions == 4:
        # 4 : 90 
        # N: 315-45, E: 45-135, S: 135-225, W: 225-315
        directions = ["N", "E", "S", "W"]
        index = round(bearing_deg / 90) % 4
    else:
        # 8 : 45 
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        index = round(bearing_deg / 45) % 8
    return directions[index]


# ==================== TSP  ====================

class TripOptimizer:
    """,OR-ToolsTSP"""

    def __init__(self):
        pass

    def optimize_trip(self, distance_matrix: List[List[Dict[str, Any]]],
                     location_names: List[str],
                     visit_durations: Dict[str, float] = None,
                     start_location_idx: int = 0,
                     total_time_available: float = None,
                     start_time: str = None) -> Dict[str, Any]:
        """
        

        Args:
            distance_matrix: ,distance()duration()
            location_names: 
            visit_durations: ()
            start_location_idx: 
            total_time_available: ()
            start_time: ("8:00")

        Returns:
            ,,
        """
        if not distance_matrix or len(distance_matrix) < 2:
            return {"error": "2"}

        try:
            # ()
            time_matrix = self._extract_time_matrix(distance_matrix)

            # ,
            if visit_durations:
                time_matrix = self._add_visit_durations(time_matrix, location_names, visit_durations)

            # OR-ToolsTSP
            if len(location_names) <= 3:
                # ,
                solution = self._solve_small_tsp(time_matrix, location_names, start_location_idx)
            else:
                # OR-Tools
                solution = self._solve_tsp_ortools(time_matrix, location_names, start_location_idx)

            # 
            if total_time_available:
                solution = self._validate_time_constraints(
                    solution, total_time_available, start_time
                )

                # P1-1: ,
                if solution.get("time_constraint_violated"):
                    print(f"[TripOptimizer] TSP ({solution.get('time_needed'):.1f}h > {total_time_available:.1f}h),...")
                    greedy_solution = self._greedy_feasible_solution(
                        time_matrix, location_names, start_location_idx, total_time_available,
                        visit_durations  # 
                    )
                    # 
                    solution["full_solution"] = {
                        "route": solution.get("route"),
                        "total_time_hours": solution.get("time_needed")
                    }
                    # 
                    solution.update(greedy_solution)
                    solution["time_constraint_violated"] = False  # 

            # 
            solution = self._calculate_route_details(
                solution, distance_matrix, location_names, visit_durations
            )

            return solution

        except Exception as e:
            return {"error": f": {str(e)}"}

    def _extract_time_matrix(self, distance_matrix: List[List[Dict[str, Any]]]) -> List[List[int]]:
        """"""
        n = len(distance_matrix)
        time_matrix = [[0] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    time_matrix[i][j] = 0
                elif distance_matrix[i][j] is not None:
                    time_matrix[i][j] = distance_matrix[i][j]['duration']
                else:
                    # ,
                    time_matrix[i][j] = 999999

        return time_matrix

    def _add_visit_durations(self, time_matrix: List[List[int]],
                           location_names: List[str],
                           visit_durations: Dict[str, float]) -> List[List[int]]:
        """"""
        n = len(time_matrix)
        new_matrix = [row[:] for row in time_matrix]

        for i in range(n):
            location_name = location_names[i]
            if location_name in visit_durations:
                visit_time_seconds = int(visit_durations[location_name] * 3600)
                # 
                for j in range(n):
                    if i != j:
                        new_matrix[i][j] += visit_time_seconds

        return new_matrix

    def _solve_small_tsp(self, time_matrix: List[List[int]],
                        location_names: List[str],
                        start_idx: int) -> Dict[str, Any]:
        """TSP()"""
        from itertools import permutations

        n = len(location_names)
        if n <= 1:
            return {
                "route": [0],
                "location_order": [location_names[0]],
                "total_time_seconds": 0,
                "feasible": True
            }

        other_indices = [i for i in range(n) if i != start_idx]
        best_route = None
        best_time = float('inf')

        # 
        for perm in permutations(other_indices):
            route = [start_idx] + list(perm)
            total_time = 0

            for i in range(len(route) - 1):
                total_time += time_matrix[route[i]][route[i + 1]]

            if total_time < best_time:
                best_time = total_time
                best_route = route

        return {
            "route": best_route,
            "location_order": [location_names[i] for i in best_route],
            "total_time_seconds": best_time,
            "feasible": True
        }

    def _solve_tsp_ortools(self, time_matrix: List[List[int]],
                          location_names: List[str],
                          start_idx: int) -> Dict[str, Any]:
        """OR-ToolsTSP"""
        n = len(time_matrix)

        # 
        manager = pywrapcp.RoutingIndexManager(n, 1, start_idx)
        routing = pywrapcp.RoutingModel(manager)

        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return time_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # 
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 10

        # 
        solution = routing.SolveWithParameters(search_parameters)

        if solution:
            # 
            route = []
            index = routing.Start(0)
            while not routing.IsEnd(index):
                route.append(manager.IndexToNode(index))
                index = solution.Value(routing.NextVar(index))

            return {
                "route": route,
                "location_order": [location_names[i] for i in route],
                "total_time_seconds": solution.ObjectiveValue(),
                "feasible": True
            }
        else:
            return {
                "error": "",
                "feasible": False
            }

    def _greedy_feasible_solution(self, time_matrix: List[List[int]],
                                  location_names: List[str],
                                  start_idx: int,
                                  total_time_available: float,
                                  visit_durations: Dict[str, float] = None) -> Dict[str, Any]:
        """
         - 

        :
        1. ()
        2. 
        3. 

        Args:
            time_matrix: (),
            location_names: 
            start_idx: 
            total_time_available: ()
            visit_durations: ()

        Returns:
            ,
        """
        n = len(location_names)
        total_time_budget = total_time_available * 3600  # 

        # ()
        visit_time_seconds = {}
        if visit_durations:
            for name, hours in visit_durations.items():
                visit_time_seconds[name] = int(hours * 3600)

        #  time_matrix 
        # time_matrix[i][j] = travel_time(i->j) + visit_duration(i)
        #  pure_travel_time[i][j] = time_matrix[i][j] - visit_duration(i)
        pure_travel_matrix = [[0] * n for _ in range(n)]
        for i in range(n):
            loc_name = location_names[i]
            visit_time = visit_time_seconds.get(loc_name, 0)
            for j in range(n):
                if i != j:
                    pure_travel_matrix[i][j] = max(0, time_matrix[i][j] - visit_time)

        # 1: ()
        greedy_result = self._greedy_nearest_neighbor(
            pure_travel_matrix, location_names, start_idx,
            total_time_budget, visit_time_seconds
        )

        # 2:  k ()
        if n <= 6:
            best_result = self._exhaustive_feasible_search(
                pure_travel_matrix, location_names, start_idx,
                total_time_budget, visit_time_seconds
            )
            # 
            if best_result["feasible_locations"] > greedy_result["feasible_locations"]:
                return best_result
            elif best_result["feasible_locations"] == greedy_result["feasible_locations"]:
                # ,
                if best_result["total_time_seconds"] < greedy_result["total_time_seconds"]:
                    return best_result

        return greedy_result

    def _greedy_nearest_neighbor(self, travel_matrix: List[List[int]],
                                  location_names: List[str],
                                  start_idx: int,
                                  total_time_budget: int,
                                  visit_time_seconds: Dict[str, int]) -> Dict[str, Any]:
        """"""
        n = len(location_names)
        route = [start_idx]
        unvisited = set(range(n)) - {start_idx}
        total_time = 0
        current_idx = start_idx

        while unvisited:
            # 
            best_candidate = None
            best_added_time = float('inf')

            for candidate_idx in unvisited:
                loc_name = location_names[candidate_idx]
                travel_time = travel_matrix[current_idx][candidate_idx]
                visit_time = visit_time_seconds.get(loc_name, 0)

                #  =  + 
                added_time = travel_time + visit_time

                if added_time < best_added_time:
                    best_added_time = added_time
                    best_candidate = candidate_idx

            if best_candidate is None:
                break

            # 
            if total_time + best_added_time > total_time_budget:
                break

            # 
            route.append(best_candidate)
            unvisited.remove(best_candidate)
            total_time += best_added_time
            current_idx = best_candidate

        feasible_count = len(route) - 1  # 

        return {
            "route": route,
            "location_order": [location_names[i] for i in route],
            "total_time_seconds": total_time,
            "feasible": True,
            "greedy_solution": True,
            "feasible_locations": feasible_count,
            "suggestion": f": {total_time_budget/3600:.1f}  {feasible_count} "
        }

    def _exhaustive_feasible_search(self, travel_matrix: List[List[int]],
                                     location_names: List[str],
                                     start_idx: int,
                                     total_time_budget: int,
                                     visit_time_seconds: Dict[str, int]) -> Dict[str, Any]:
        """
        :

        (n <= 6),
        """
        from itertools import permutations, combinations

        n = len(location_names)
        other_indices = [i for i in range(n) if i != start_idx]

        best_result = {
            "route": [start_idx],
            "location_order": [location_names[start_idx]],
            "total_time_seconds": 0,
            "feasible": True,
            "greedy_solution": False,
            "feasible_locations": 0,
            "suggestion": ""
        }

        # 
        for k in range(len(other_indices), 0, -1):
            found_feasible = False

            #  k 
            for subset in combinations(other_indices, k):
                #  k 
                for perm in permutations(subset):
                    route = [start_idx] + list(perm)
                    total_time = 0
                    feasible = True

                    # 
                    for i in range(len(route) - 1):
                        from_idx = route[i]
                        to_idx = route[i + 1]
                        loc_name = location_names[to_idx]

                        travel_time = travel_matrix[from_idx][to_idx]
                        visit_time = visit_time_seconds.get(loc_name, 0)

                        total_time += travel_time + visit_time

                        if total_time > total_time_budget:
                            feasible = False
                            break

                    if feasible:
                        found_feasible = True
                        # 
                        if k > best_result["feasible_locations"] or \
                           (k == best_result["feasible_locations"] and total_time < best_result["total_time_seconds"]):
                            best_result = {
                                "route": route,
                                "location_order": [location_names[i] for i in route],
                                "total_time_seconds": total_time,
                                "feasible": True,
                                "greedy_solution": False,
                                "feasible_locations": k,
                                "suggestion": f": {total_time_budget/3600:.1f}  {k} "
                            }

            #  k ,
            if found_feasible and k == best_result["feasible_locations"]:
                break

        return best_result

    def _validate_time_constraints(self, solution: Dict[str, Any],
                                 total_time_available: float,
                                 start_time: str = None) -> Dict[str, Any]:
        """"""
        if not solution.get("feasible"):
            return solution

        total_time_hours = solution["total_time_seconds"] / 3600

        if total_time_hours > total_time_available:
            solution["time_constraint_violated"] = True
            solution["time_needed"] = total_time_hours
            solution["time_available"] = total_time_available

            # P1-1: ,
            solution["suggestion"] = f" {total_time_hours:.1f} , {total_time_available:.1f} .."
        else:
            solution["time_constraint_violated"] = False

        if start_time:
            solution["estimated_end_time"] = self._calculate_end_time(start_time, total_time_hours)

        return solution

    def _calculate_end_time(self, start_time: str, duration_hours: float) -> str:
        """"""
        try:
            start_hour, start_minute = map(int, start_time.split(':'))
            start_dt = datetime.datetime.now().replace(hour=start_hour, minute=start_minute)
            end_dt = start_dt + datetime.timedelta(hours=duration_hours)
            return end_dt.strftime("%H:%M")
        except:
            return ""

    def _calculate_route_details(self, solution: Dict[str, Any],
                               distance_matrix: List[List[Dict[str, Any]]],
                               location_names: List[str],
                               visit_durations: Dict[str, float] = None) -> Dict[str, Any]:
        """"""
        if not solution.get("feasible") or not solution.get("route"):
            return solution

        route = solution["route"]
        details = []
        total_distance = 0

        for i in range(len(route) - 1):
            from_idx = route[i]
            to_idx = route[i + 1]

            if distance_matrix[from_idx][to_idx]:
                leg_info = distance_matrix[from_idx][to_idx]
                # P1-1: distance_textduration_text(haversine fallback)
                details.append({
                    "from": location_names[from_idx],
                    "to": location_names[to_idx],
                    "distance": leg_info["distance"],
                    "duration": leg_info["duration"],
                    "distance_text": leg_info.get("distance_text", f"{leg_info['distance']/1000:.1f} km"),
                    "duration_text": leg_info.get("duration_text", f"{leg_info['duration']//60} mins")
                })
                total_distance += leg_info["distance"]

        solution["route_details"] = details
        solution["total_distance_meters"] = total_distance
        solution["total_distance_text"] = f"{total_distance/1000:.1f} km"

        return solution