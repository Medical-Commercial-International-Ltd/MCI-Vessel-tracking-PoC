"""Provisional retrospective movement indicators, never an inference of intent."""
from math import asin, atan2, cos, degrees, radians, sin

from app.ais_data import bearing_degrees, haversine_nm
from app.models import StormBehaviour


def distance(a, b):
    return haversine_nm(a.latitude, a.longitude, b.latitude, b.longitude)


def projected_distance(origin, heading, travel_nm, target):
    lat, lon, heading = radians(origin.latitude), radians(origin.longitude), radians(heading)
    arc = travel_nm / 3440.065
    end_lat = asin(sin(lat) * cos(arc) + cos(lat) * sin(arc) * cos(heading))
    end_lon = lon + atan2(sin(heading) * sin(arc) * cos(lat), cos(arc) - sin(lat) * sin(end_lat))
    return haversine_nm(degrees(end_lat), degrees(end_lon), target.latitude, target.longitude)


def assess_behaviour(intervals, storm, proximity_nm):
    result = StormBehaviour(proximity_nm=proximity_nm)
    previous = None
    supported = 0
    for left, right in intervals:
        hours = (right.timestamp - left.timestamp).total_seconds() / 3600
        a, b = storm.at(left.timestamp), storm.at(right.timestamp)
        if not (0 < hours <= 6) or a is None or b is None:
            previous = None
            continue
        start_distance, end_distance = distance(left, a), distance(right, b)
        travel = distance(left, right)
        speed = travel / hours
        heading = bearing_degrees(left.latitude, left.longitude, right.latitude, right.longitude)
        near = min(start_distance, end_distance) <= proximity_nm
        if near:
            supported += 1
            # Require both endpoints in range to avoid counting an entire boundary crossing.
            if speed <= 1 and max(start_distance, end_distance) <= proximity_nm:
                result.stationary_hours += hours
                # Storm moves toward the fixed starting location, independent of vessel drift.
                closing = start_distance - distance(left, b)
                if closing >= 5 or (b.wind_kt >= a.wind_kt + 10 and end_distance <= start_distance):
                    result.stationary_worsening_hours += hours
            if previous and previous[1] == left and speed > 1:
                old_left, _, old_heading, old_speed, old_distance = previous
                turn = abs((heading - old_heading + 180) % 360 - 180)
                continued = projected_distance(left, old_heading, old_speed * hours, b)
                # Approach before turn; meaningful turn; separation grows and beats continuation.
                if (old_speed > 1 and old_distance - start_distance >= 5 and turn >= 30
                        and end_distance - start_distance >= 5 and end_distance - continued >= 10):
                    result.avoidance_manoeuvres += 1
        previous = (left, right, heading, speed, start_distance)
    result.status = "ASSESSED" if supported else "INSUFFICIENT"
    penalty = min(20, round(result.stationary_worsening_hours * 5))
    credit = min(10, result.avoidance_manoeuvres * 5)
    result.adjustment = penalty - credit
    result.stationary_hours = round(result.stationary_hours, 1)
    result.stationary_worsening_hours = round(result.stationary_worsening_hours, 1)
    if not supported:
        result.findings.append("Insufficient continuous tracking near this storm to assess movement; no adjustment.")
    else:
        result.findings.append(f"{result.stationary_hours:g} h stationary at no more than 1 kt within {proximity_nm:g} nm.")
        result.findings.append(f"{result.stationary_worsening_hours:g} h stationary while the storm approached or intensified.")
        result.findings.append(f"{result.avoidance_manoeuvres} course changes consistent with avoidance.")
    result.findings.append("Retrospective track estimates do not establish intent, forecast awareness, shelter or the safety of an alternative route.")
    return result
