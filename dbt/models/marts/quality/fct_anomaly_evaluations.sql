-- Fault-injection benchmark of the anomaly detectors (make evaluate, core/anomaly/evaluation.py): one row per run,
-- source, detector and fault kind, plus fault = 'all' with the totals and the precision. is_latest marks the newest
-- run of each source, the one the API and the web show.
with evaluations as (
    select * from {{ ref('stg_quality__anomaly_evaluations') }}
),

runs as (
    select
        source,
        run_id,
        max(evaluated_at) as evaluated_at
    from evaluations
    group by source, run_id
),

ranked as (
    select
        source,
        run_id,
        row_number() over (partition by source order by evaluated_at desc, run_id desc) as rn
    from runs
)

select
    evaluations.run_id,
    evaluations.source,
    evaluations.detector,
    evaluations.fault,
    evaluations.window_start,
    evaluations.window_end,
    evaluations.seed,
    evaluations.series,
    evaluations.events,
    evaluations.events_detected,
    evaluations.points,
    evaluations.points_detected,
    evaluations.recall,
    evaluations.event_recall,
    evaluations.false_alarms,
    evaluations.baseline_flags,
    evaluations.precision,
    evaluations.evaluated_at,
    ranked.rn = 1 as is_latest
from evaluations
inner join ranked
    on evaluations.source = ranked.source and evaluations.run_id = ranked.run_id
