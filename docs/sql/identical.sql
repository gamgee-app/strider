with md5_theatrical as (select hash_md5
                        from two_towers_theatrical
                        group by hash_md5
                        having count(1) = 1),
     md5_extended as (select hash_md5
                      from two_towers_extended
                      group by hash_md5
                      having count(1) = 1),
     md5_unique_hash as (select hash_md5
                         from md5_theatrical
                         intersect
                         select hash_md5
                         from md5_extended),
     md5_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                 two_towers_extended.frame_index   as extended_index
                          from two_towers_theatrical
                                   join two_towers_extended
                                        on two_towers_theatrical.hash_md5 = two_towers_extended.hash_md5
                          where two_towers_theatrical.hash_md5 in md5_unique_hash),
     md5_invalid_orderings as (select *
                               from (select extended_index,
                                            LAG(extended_index) over (order by theatrical_index) as prev_extended
                                     from md5_unique_index) t
                               where extended_index < prev_extended),

     average_theatrical as (select hash_average
                            from two_towers_theatrical
                            group by hash_average
                            having count(1) = 1),
     average_extended as (select hash_average
                          from two_towers_extended
                          group by hash_average
                          having count(1) = 1),
     average_unique_hash as (select hash_average
                             from average_theatrical
                             intersect
                             select hash_average
                             from average_extended),
     average_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                     two_towers_extended.frame_index   as extended_index
                              from two_towers_theatrical
                                       join two_towers_extended
                                            on two_towers_theatrical.hash_average = two_towers_extended.hash_average
                              where two_towers_theatrical.hash_average in average_unique_hash),
     average_invalid_orderings as (select *
                                   from (select extended_index,
                                                LAG(extended_index) over (order by theatrical_index) as prev_extended
                                         from average_unique_index) t
                                   where extended_index < prev_extended),

     perceptual_theatrical as (select hash_perceptual
                               from two_towers_theatrical
                               group by hash_perceptual
                               having count(1) = 1),
     perceptual_extended as (select hash_perceptual
                             from two_towers_extended
                             group by hash_perceptual
                             having count(1) = 1),
     perceptual_unique_hash as (select hash_perceptual
                                from perceptual_theatrical
                                intersect
                                select hash_perceptual
                                from perceptual_extended),
     perceptual_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                        two_towers_extended.frame_index   as extended_index
                                 from two_towers_theatrical
                                          join two_towers_extended
                                               on two_towers_theatrical.hash_perceptual =
                                                  two_towers_extended.hash_perceptual
                                 where two_towers_theatrical.hash_perceptual in perceptual_unique_hash),
     perceptual_invalid_orderings as (select *
                                      from (select extended_index,
                                                   LAG(extended_index) over (order by theatrical_index) as prev_extended
                                            from perceptual_unique_index) t
                                      where extended_index < prev_extended),

     marr_hildreth_theatrical as (select hash_marr_hildreth
                                  from two_towers_theatrical
                                  group by hash_marr_hildreth
                                  having count(1) = 1),
     marr_hildreth_extended as (select hash_marr_hildreth
                                from two_towers_extended
                                group by hash_marr_hildreth
                                having count(1) = 1),
     marr_hildreth_unique_hash as (select hash_marr_hildreth
                                   from marr_hildreth_theatrical
                                   intersect
                                   select hash_marr_hildreth
                                   from marr_hildreth_extended),
     marr_hildreth_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                           two_towers_extended.frame_index   as extended_index
                                    from two_towers_theatrical
                                             join two_towers_extended
                                                  on two_towers_theatrical.hash_marr_hildreth =
                                                     two_towers_extended.hash_marr_hildreth
                                    where two_towers_theatrical.hash_marr_hildreth in marr_hildreth_unique_hash),
     marr_hildreth_invalid_orderings as (select *
                                         from (select extended_index,
                                                      LAG(extended_index) over (order by theatrical_index) as prev_extended
                                               from marr_hildreth_unique_index) t
                                         where extended_index < prev_extended),

     radial_variance_theatrical as (select hash_radial_variance
                                    from two_towers_theatrical
                                    group by hash_radial_variance
                                    having count(1) = 1),
     radial_variance_extended as (select hash_radial_variance
                                  from two_towers_extended
                                  group by hash_radial_variance
                                  having count(1) = 1),
     radial_variance_unique_hash as (select hash_radial_variance
                                     from radial_variance_theatrical
                                     intersect
                                     select hash_radial_variance
                                     from radial_variance_extended),
     radial_variance_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                             two_towers_extended.frame_index   as extended_index
                                      from two_towers_theatrical
                                               join two_towers_extended
                                                    on two_towers_theatrical.hash_radial_variance =
                                                       two_towers_extended.hash_radial_variance
                                      where two_towers_theatrical.hash_radial_variance in radial_variance_unique_hash),
     radial_variance_invalid_orderings as (select *
                                           from (select extended_index,
                                                        LAG(extended_index) over (order by theatrical_index) as prev_extended
                                                 from radial_variance_unique_index) t
                                           where extended_index < prev_extended),

     block_mean_theatrical as (select hash_block_mean_0
                               from two_towers_theatrical
                               group by hash_block_mean_0
                               having count(1) = 1),
     block_mean_extended as (select hash_block_mean_0
                             from two_towers_extended
                             group by hash_block_mean_0
                             having count(1) = 1),
     block_mean_unique_hash as (select hash_block_mean_0
                                from block_mean_theatrical
                                intersect
                                select hash_block_mean_0
                                from block_mean_extended),
     block_mean_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                        two_towers_extended.frame_index   as extended_index
                                 from two_towers_theatrical
                                          join two_towers_extended
                                               on two_towers_theatrical.hash_block_mean_0 =
                                                  two_towers_extended.hash_block_mean_0
                                 where two_towers_theatrical.hash_block_mean_0 in block_mean_unique_hash),
     block_mean_invalid_orderings as (select *
                                      from (select extended_index,
                                                   LAG(extended_index) over (order by theatrical_index) as prev_extended
                                            from block_mean_unique_index) t
                                      where extended_index < prev_extended),

     union_unique as (select theatrical_index, extended_index
                      from md5_unique_index
                      union
                      select theatrical_index, extended_index
                      from average_unique_index
                      union
                      select theatrical_index, extended_index
                      from perceptual_unique_index
                      union
                      select theatrical_index, extended_index
                      from marr_hildreth_unique_index
                      union
                      select theatrical_index, extended_index
                      from radial_variance_unique_index
                      union
                      select theatrical_index, extended_index
                      from block_mean_unique_index),
     union_unique_deduplicated as (select theatrical_index, extended_index
                                   from (select t.*, count(1) over (partition by theatrical_index) count
                                         from union_unique t) t
                                   where count = 1),
     union_unique_deduplicated_invalid_orderings as (select *
                                                     from (select extended_index,
                                                                  LAG(extended_index) over (order by theatrical_index) as prev_extended
                                                           from union_unique_deduplicated) t
                                                     where extended_index < prev_extended),
     union_unique_deduplicated_validated as (select *
                                             from union_unique_deduplicated
                                             where extended_index not in (select extended_index
                                                                          from union_unique_deduplicated_invalid_orderings
                                                                          union
                                                                          select prev_extended
                                                                          from union_unique_deduplicated_invalid_orderings)),
     union_unique_deduplicated_validity_compared as (select 'union_all'                                                   as Algorithm,
                                                            (select count(1) from union_unique_deduplicated)              as "Count Unvalidated",
                                                            count(1)                                                      as "Count Validated",
                                                            printf("%.2f%", 100.0 * count(1) /
                                                                            (select count(1) from two_towers_theatrical)) as "Percentage Validated Theatrical",
                                                            printf("%.2f%", 100.0 * count(1) /
                                                                            (select count(1) from two_towers_extended))   as "Percentage Validated Extended"
                                                     from union_unique_deduplicated_validated),

     invalid_orderings as (select 'md5'                                                         as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from md5_invalid_orderings
                           union
                           select 'average'                                                     as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from average_invalid_orderings
                           union
                           select 'perceptual'                                                  as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from perceptual_invalid_orderings
                           union
                           select 'marr_hildreth'                                               as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from marr_hildreth_invalid_orderings
                           union
                           select 'radial_variance'                                             as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from radial_variance_invalid_orderings
                           union
                           select 'block_mean'                                                  as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from block_mean_invalid_orderings
                           union
                           select 'union_all'                                                   as algorithm,
                                  count(1)                                                      as invalid_count,
                                  printf("%.2f%", 100.0 * count(1) /
                                                  (select count(1) from two_towers_theatrical)) as percentage_invalid
                           from union_unique_deduplicated_invalid_orderings
                           order by invalid_count desc),

     algorithms_compared as (select 'md5'                                                         as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from md5_unique_index

                             union

                             select 'average'                                                     as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from average_unique_index

                             union

                             select 'perceptual'                                                  as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from perceptual_unique_index

                             union

                             select 'marr_hildreth'                                               as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from marr_hildreth_unique_index

                             union

                             select 'radial_variance'                                             as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from radial_variance_unique_index

                             union

                             select 'block_mean'                                                  as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from block_mean_unique_index

                             union

                             select 'union_all'                                                   as algorithm,
                                    count(1)                                                      as count,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_theatrical)) as percentage_theatrical,
                                    printf("%.2f%", 100.0 * count(1) /
                                                    (select count(1) from two_towers_extended))   as percentage_extended
                             from union_unique_deduplicated

                             order by count desc),

     extended_chapters as (select * from two_towers_extended_chapters),

     extended_seconds(extended_second) AS (SELECT 0 AS extended_second
                                           UNION ALL
                                           SELECT extended_second + 1
                                           FROM extended_seconds
                                           WHERE extended_second < (SELECT MAX(floor(extended_index / (24)))
                                                                    FROM union_unique_deduplicated_validated)),

     per_second as (select count(1)              as count,
                           100.0 * count(1) / 24 as percentage,
                           theatrical_index / 24 as theatrical_second,
                           extended_index / 24   as extended_second
                    from union_unique_deduplicated_validated
                    group by floor(extended_index / 24)),

     per_second_including_empties
         as (select coalesce(per_second.count, 0)                                          as "Count Common per Extended Second",
                    printf("%.2f%", coalesce(per_second.percentage, 0))                    as "Percentage Common per Extended Second",
                    time(per_second.theatrical_second, 'unixepoch')                        as 'Theatrical Second',
                    time(coalesce(per_second.extended_second, extended_seconds.extended_second),
                         'unixepoch')                                                      as "Extended Second",
                    coalesce(per_second.extended_second, extended_seconds.extended_second) as extended_second
             from extended_seconds
                      left join per_second
                                on extended_seconds.extended_second = per_second.extended_second
             order by extended_seconds.extended_second),

     missing_seconds AS (
         -- Find seconds that are missing from the dataset
         SELECT extended_second
         FROM extended_seconds
         WHERE extended_second NOT IN (SELECT extended_second FROM per_second)),

     grouped_second_gaps AS (
         -- Identify contiguous missing second groups using a difference-based technique
         SELECT extended_second,
                extended_second - ROW_NUMBER() OVER (ORDER BY extended_second) AS gap_group
         FROM missing_seconds),

     missing_second_ranges as (
         -- Identify start and end of each missing range
         SELECT MIN(extended_second)                                                 AS range_start,
                1 + MAX(extended_second)                                             AS range_end,
                1 + MAX(extended_second) - MIN(extended_second)                      as duration,
                time(MIN(extended_second), 'unixepoch')                              as range_start_time,
                time(1 + MAX(extended_second), 'unixepoch')                          as range_end_time,
                time((1 + MAX(extended_second) - MIN(extended_second)), 'unixepoch') as duration_time
         FROM grouped_second_gaps
         GROUP BY gap_group
         ORDER BY range_start),

     missing_second_ranges_with_chapter
         as (select range_start_time as 'Range Start Time',
                    range_end_time   as 'Range End Time',
                    duration_time    as 'Duration',
                    (select title
                     from extended_chapters
                     where time(start_time) <= range_start_time
                     order by time(start_time) desc
                     limit 1)        as 'Matched Chapter'
             from missing_second_ranges),

     extended_minutes(extended_minute) AS (SELECT 0 AS extended_minute
                                           UNION ALL
                                           SELECT extended_minute + 1
                                           FROM extended_minutes
                                           WHERE extended_minute < (SELECT MAX(floor(extended_index / (24 * 60)))
                                                                    FROM union_unique_deduplicated_validated)),

     per_minute as (select count(1)                     as count,
                           100.0 * count(1) / (24 * 60) as percentage,
                           theatrical_index / (24 * 60) as theatrical_minute,
                           extended_index / (24 * 60)   as extended_minute
                    from union_unique_deduplicated_validated
                    group by floor(extended_index / (24 * 60))),

     per_minute_including_empties
         as (select coalesce(per_minute.count, 0)                        as "Count Common per Extended Minute",
                    printf("%.2f%", coalesce(per_minute.percentage, 0))  as "Percentage Common per Extended Minute",
                    time(per_minute.theatrical_minute * 60, 'unixepoch') as 'Theatrical Minute',
                    time(coalesce(per_minute.extended_minute, extended_minutes.extended_minute) * 60,
                         'unixepoch')                                    as "Extended Minute"
             from extended_minutes
                      left join per_minute
                                on extended_minutes.extended_minute = per_minute.extended_minute
             order by extended_minutes.extended_minute),

     missing_minutes AS (
         -- Find minutes that are missing from the dataset
         SELECT extended_minute
         FROM extended_minutes
         WHERE extended_minute NOT IN (SELECT extended_minute FROM per_minute)),

     grouped_minute_gaps AS (
         -- Identify contiguous missing minute groups using a difference-based technique
         SELECT extended_minute,
                extended_minute - ROW_NUMBER() OVER (ORDER BY extended_minute) AS gap_group
         FROM missing_minutes),

     missing_minute_ranges as (
         -- Identify start and end of each missing range
         SELECT MIN(extended_minute)                                                      AS range_start,
                1 + MAX(extended_minute)                                                  AS range_end,
                1 + MAX(extended_minute) - MIN(extended_minute)                           as duration,
                time(MIN(extended_minute) * 60, 'unixepoch')                              as range_start_time,
                time((1 + MAX(extended_minute)) * 60, 'unixepoch')                        as range_end_time,
                time((1 + MAX(extended_minute) - MIN(extended_minute)) * 60, 'unixepoch') as duration_time
         FROM grouped_minute_gaps
         GROUP BY gap_group
         ORDER BY range_start),

     missing_minute_ranges_with_chapter
         as (select range_start_time as 'Range Start Time',
                    range_end_time   as 'Range End Time',
                    duration_time    as 'Duration',
                    (select title
                     from extended_chapters
                     where time(start_time) <= range_start_time
                     order by time(start_time) desc
                     limit 1)        as 'Matched Chapter'
             from missing_minute_ranges)

select *
from missing_second_ranges_with_chapter
;
