"""Research-backed demo case selection. No investigation is an imported AIS track."""
from urllib.parse import urlencode


CASES = [
    dict(name='EL FARO (cargo reference)', mmsi='368208000', start='2015-09-29', end='2015-10-01', proximity=200,
         purpose='Recorded approach into Joaquin',
         evidence='NOAA coastal AIS plus NTSB VDR positions cover the final approach. The movement calculation uses original recorded positions; the historical-loss recommendation also cites the completed NTSB investigation.'),
    dict(name='JODI ANN', mmsi='339857000', start='2023-01-01', end='2025-12-31', proximity=200,
         purpose='Favourable weather discussion',
         evidence='The refreshed assessment found no qualifying encounters in the supported tracks. Review coverage and current crew before offering terms.'),
    dict(name='LADY ELANE', mmsi='339078000', start='2023-01-01', end='2025-12-31', proximity=200,
         purpose='Potential offer with conditions',
         evidence='An elevated weather example below the high-risk referral threshold. Current crew findings can still change the recommendation.'),
    dict(name='AZULITA', mmsi='368001090', start='2023-10-03', end='2023-10-03', proximity=70,
         purpose='Movement away from Philippe',
         evidence='Original broadcasts: separation increased from 65.01 to 77.62 nm. Vessel movement contributed +23.45 nm compared with remaining at the starting position. One day does not establish a long-term risk history.'),
    dict(name='A1A', mmsi='368281860', start='2023-10-03', end='2023-10-03', proximity=70,
         purpose='Movement towards Philippe',
         evidence='Original broadcasts: an approach window reduced separation from 61.18 to 21.07 nm; vessel movement contributed -10.08 nm. Earlier movement increased separation. This mixed response calls for review, not a claim of reckless navigation.'),
    dict(name='SERENITY (AIS-reported)', mmsi='367733210', start='2023-09-23', end='2023-09-23', proximity=70,
         purpose='Severe exposure; harbour context',
         evidence='Stationary in the Morehead City / Beaufort harbour area during Ophelia. The current model adds 20 points for stationary approach. Review shelter protection before interpreting the severe score; this is not movement into a storm.'),
    dict(name='LEGACY (AIS-reported)', mmsi='319920000', start='2023-09-23', end='2023-09-23', proximity=70,
         purpose='Severe exposure; anchorage context',
         evidence='Stationary in the Wrightsville Beach anchorage area during Ophelia. The current model adds 20 points for stationary approach. Shelter and storm planning require review; moving may not have been safer.'),
]


def local_cases(analyses):
    rows = []
    for case in CASES:
        matches = [a for a in analyses if not a.is_synthetic and a.status == 'completed'
                   and case['mmsi'] in a.vessel.mmsi
                   and a.input.period.from_date.isoformat() == case['start']
                   and a.input.period.to_date.isoformat() == case['end']
                   and a.input.storm_proximity_nm == case['proximity']
                   and a.risk.model_version == 'TC-EXPOSURE-v0.5']
        analysis = max(matches, key=lambda a: a.created_at) if matches else None
        query = urlencode(dict(mmsi=case['mmsi'], fromDate=case['start'], toDate=case['end']))
        rows.append({**case, 'analysis': analysis,
                     'url': '/analysis?analysisId=' + analysis.analysis_id if analysis else '/analysis?' + query})
    return rows
