-- theatrical unique
select count(1)                                                                         as 'Unique Frames',
       (select count(1) from two_towers_theatrical)                                     as 'Total Frames',
       printf("%.2f%", 100.0 * count(1) / (select count(1) from two_towers_theatrical)) as 'Percentage'
from (select md5_hash
      from two_towers_theatrical
      group by md5_hash
      having count(1) = 1);

-- extended unique
select count(1)                                                                       as 'Unique Frames',
       (select count(1) from two_towers_extended)                                     as 'Total Frames',
       printf("%.2f%", 100.0 * count(1) / (select count(1) from two_towers_extended)) as 'Percentage'
from (select md5_hash
      from two_towers_extended
      group by md5_hash
      having count(1) = 1);

-- intersected unique
select count(1)                                                                         as 'Unique Common Frames',
       (select count(1) from two_towers_theatrical)                                     as 'Total Theatrical Frames',
       printf("%.2f%", 100.0 * count(1) / (select count(1) from two_towers_theatrical)) as 'Percentage Theatrical',
       (select count(1) from two_towers_extended)                                       as 'Total Extended Frames',
       printf("%.2f%", 100.0 * count(1) / (select count(1) from two_towers_extended))   as 'Percentage Extended'
from (select md5_hash
      from two_towers_theatrical
      group by md5_hash
      having count(1) = 1

      intersect

      select md5_hash
      from two_towers_extended
      group by md5_hash
      having count(1) = 1);

-- common frames per minute
select count(1)                                                                                as 'Count Common per Theatrical Minute',
       printf("%.2f%", 100.0 * count(1) / (24 * 60))                                           as 'Percentage Common per Theatrical Minute',
       time(round(ttt.frame_index / 24, 0) - round(ttt.frame_index / 24, 0) % 60, 'unixepoch') as 'Theatrical Minute',
       time(round(tte.frame_index / 24, 0) - round(tte.frame_index / 24, 0) % 60, 'unixepoch') as 'Extended Minute'
from two_towers_theatrical ttt
         inner join two_towers_extended tte on tte.md5_hash = ttt.md5_hash
where ttt.md5_hash in (select md5_hash
                       from two_towers_theatrical
                       group by md5_hash
                       having count(1) = 1

                       intersect

                       select md5_hash
                       from two_towers_extended
                       group by md5_hash
                       having count(1) = 1)
group by round(ttt.frame_index / (24 * 60), 0);

-- common frames per minute, bucketed
select printf("%d%", floor("Percentage Common per Theatrical Minute" / 10) * 10) as 'Bucket',
       count(1)                                                                  as 'Count'
from (select 100.0 * count(1) / (24 * 60) as 'Percentage Common per Theatrical Minute'
      from two_towers_theatrical ttt
               inner join two_towers_extended tte on tte.md5_hash = ttt.md5_hash
      where ttt.md5_hash in (select md5_hash
                             from two_towers_theatrical
                             group by md5_hash
                             having count(1) = 1

                             intersect

                             select md5_hash
                             from two_towers_extended
                             group by md5_hash
                             having count(1) = 1)
      group by round(ttt.frame_index / (24 * 60), 0))
group by floor("Percentage Common per Theatrical Minute" / 10)