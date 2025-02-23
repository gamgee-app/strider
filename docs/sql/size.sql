SELECT
    83304730527 as 'Theatrical File Size',
    (SELECT SUM("pgsize") FROM "dbstat" WHERE name='two_towers_theatrical') as 'Theatrical Hashes Size',
    printf("%.2f%", 100.0 * (SELECT SUM("pgsize") FROM "dbstat" WHERE name='two_towers_theatrical') / 120576935820) as 'Theatrical Shrinkage',
    120576935820 as 'Extended File Size',
    (SELECT SUM("pgsize") FROM "dbstat" WHERE name='two_towers_extended') as 'Extended Hashes Size',
    printf("%.2f%", 100.0 * (SELECT SUM("pgsize") FROM "dbstat" WHERE name='two_towers_extended') / 120576935820) as 'Extended Shrinkage';