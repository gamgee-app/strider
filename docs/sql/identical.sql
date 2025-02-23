with md5_theatrical as (select md5_hash
                        from two_towers_theatrical
                        group by md5_hash
                        having count(1) = 1),
     md5_extended as (select md5_hash
                      from two_towers_extended
                      group by md5_hash
                      having count(1) = 1),
     md5_unique_hash as (select md5_hash
                         from md5_theatrical
                         intersect
                         select md5_hash
                         from md5_extended),
     md5_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                 two_towers_extended.frame_index   as extended_index
                          from two_towers_theatrical
                                   join two_towers_extended
                                        on two_towers_theatrical.md5_hash = two_towers_extended.md5_hash
                          where two_towers_theatrical.md5_hash in md5_unique_hash),
     md5_invalid_orderings as (select *
                               from (select extended_index,
                                            LAG(extended_index) over (order by theatrical_index) as prev_extended
                                     from md5_unique_index) t
                               where extended_index < prev_extended),

     average_theatrical as (select average_hash
                            from two_towers_theatrical
                            group by average_hash
                            having count(1) = 1),
     average_extended as (select average_hash
                          from two_towers_extended
                          group by average_hash
                          having count(1) = 1),
     average_unique_hash as (select average_hash
                             from average_theatrical
                             intersect
                             select average_hash
                             from average_extended),
     average_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                     two_towers_extended.frame_index   as extended_index
                              from two_towers_theatrical
                                       join two_towers_extended
                                            on two_towers_theatrical.average_hash = two_towers_extended.average_hash
                              where two_towers_theatrical.average_hash in average_unique_hash),
     average_invalid_orderings as (select *
                                   from (select extended_index,
                                                LAG(extended_index) over (order by theatrical_index) as prev_extended
                                         from average_unique_index) t
                                   where extended_index < prev_extended),

     perceptual_theatrical as (select perceptual_hash
                               from two_towers_theatrical
                               group by perceptual_hash
                               having count(1) = 1),
     perceptual_extended as (select perceptual_hash
                             from two_towers_extended
                             group by perceptual_hash
                             having count(1) = 1),
     perceptual_unique_hash as (select perceptual_hash
                                from perceptual_theatrical
                                intersect
                                select perceptual_hash
                                from perceptual_extended),
     perceptual_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                        two_towers_extended.frame_index   as extended_index
                                 from two_towers_theatrical
                                          join two_towers_extended
                                               on two_towers_theatrical.perceptual_hash =
                                                  two_towers_extended.perceptual_hash
                                 where two_towers_theatrical.perceptual_hash in perceptual_unique_hash),
     perceptual_invalid_orderings as (select *
                                      from (select extended_index,
                                                   LAG(extended_index) over (order by theatrical_index) as prev_extended
                                            from perceptual_unique_index) t
                                      where extended_index < prev_extended),

     marr_hildreth_theatrical as (select marr_hildreth_hash
                                  from two_towers_theatrical
                                  group by marr_hildreth_hash
                                  having count(1) = 1),
     marr_hildreth_extended as (select marr_hildreth_hash
                                from two_towers_extended
                                group by marr_hildreth_hash
                                having count(1) = 1),
     marr_hildreth_unique_hash as (select marr_hildreth_hash
                                   from marr_hildreth_theatrical
                                   intersect
                                   select marr_hildreth_hash
                                   from marr_hildreth_extended),
     marr_hildreth_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                           two_towers_extended.frame_index   as extended_index
                                    from two_towers_theatrical
                                             join two_towers_extended
                                                  on two_towers_theatrical.marr_hildreth_hash =
                                                     two_towers_extended.marr_hildreth_hash
                                    where two_towers_theatrical.marr_hildreth_hash in marr_hildreth_unique_hash),
     marr_hildreth_invalid_orderings as (select *
                                         from (select extended_index,
                                                      LAG(extended_index) over (order by theatrical_index) as prev_extended
                                               from marr_hildreth_unique_index) t
                                         where extended_index < prev_extended),

     radial_variance_theatrical as (select radial_variance_hash
                                    from two_towers_theatrical
                                    group by radial_variance_hash
                                    having count(1) = 1),
     radial_variance_extended as (select radial_variance_hash
                                  from two_towers_extended
                                  group by radial_variance_hash
                                  having count(1) = 1),
     radial_variance_unique_hash as (select radial_variance_hash
                                     from radial_variance_theatrical
                                     intersect
                                     select radial_variance_hash
                                     from radial_variance_extended),
     radial_variance_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                             two_towers_extended.frame_index   as extended_index
                                      from two_towers_theatrical
                                               join two_towers_extended
                                                    on two_towers_theatrical.radial_variance_hash =
                                                       two_towers_extended.radial_variance_hash
                                      where two_towers_theatrical.radial_variance_hash in radial_variance_unique_hash),
     radial_variance_invalid_orderings as (select *
                                           from (select extended_index,
                                                        LAG(extended_index) over (order by theatrical_index) as prev_extended
                                                 from radial_variance_unique_index) t
                                           where extended_index < prev_extended),

     block_mean_theatrical as (select block_mean_hash
                               from two_towers_theatrical
                               group by block_mean_hash
                               having count(1) = 1),
     block_mean_extended as (select block_mean_hash
                             from two_towers_extended
                             group by block_mean_hash
                             having count(1) = 1),
     block_mean_unique_hash as (select block_mean_hash
                                from block_mean_theatrical
                                intersect
                                select block_mean_hash
                                from block_mean_extended),
     block_mean_unique_index as (select two_towers_theatrical.frame_index as theatrical_index,
                                        two_towers_extended.frame_index   as extended_index
                                 from two_towers_theatrical
                                          join two_towers_extended
                                               on two_towers_theatrical.block_mean_hash =
                                                  two_towers_extended.block_mean_hash
                                 where two_towers_theatrical.block_mean_hash in block_mean_unique_hash),
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
             order by extended_minutes.extended_minute)

select *
from per_second_including_empties;
