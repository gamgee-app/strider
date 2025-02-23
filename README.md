# Movie Edition Comparer

A simple python package for finding common and unique scenes in various editions of the same movie.

- Calculate the hashes of each video frame, using various different image hashing algorithms
- Store those hashes in a database, so as not to require rehashing with updates to the comparison logic
- Compare the hashes, returning any differences found

# The Lord of the Rings

This package was made with The Lord of the Rings in mind. I have watched the extended edition movies enough times to
have forgotten which scenes are entirely new, which are extended, and which have been changed. I thought it would be
useful to document here some of my findings when trying to solve this problem.

## Pixel Perfect Identical Frames

One might assume that you could take a scene from a theatrical edition that is visually identical to a scene in its
respective extended edition, and for them to be frame-by-frame pixel perfect matches. This is not the case, at least
not for the 2020 remastered Blu-ray releases of The Lord of the Rings trilogy. It seems that even though the studio had
access to the same sources, they encoded the editions slightly differently, leading to visually identical, but not
pixel perfect scenes.

Rather than comparing pixels, I chose to compute various hashes for each frame and store them in a SQLite database, as
hashes are significantly smaller and easier to compare than full frames. The hashing algorithms I chose were MD5 (for
pixel perfect comparisons), and a select number of image specific hashing algorithms
implemented [in OpenCV](https://docs.opencv.org/4.x/d4/d93/group__img__hash.html), which were intended to be used to
score visually similar frames for imperfect matching.

All the following tables were calculated in relation to The Two Towers editions.

### File Size vs. Database Table Size

We can see significant differences in the original movie file size and the computed hashes database size.

| Edition    | File Size (bytes) | Hashes Table Size (bytes) | Shrinkage |
|:-----------|:------------------|:--------------------------|:----------|
| Theatrical | 83,304,730,527    | 105,373,696               | 0.09%     |
| Extended   | 120,576,935,820   | 126,418,944               | 0.10%     |

### Edition Lengths

The theatrical edition is roughly 23% shorter than the extended edition.

| Total Theatrical Frames | Total Extended Frames | Total Percentage Frames |
|:------------------------|:----------------------|:------------------------|
| 258,097                 | 338,641               | 76.74%                  |

### Unique Frames

Unique frames here are frames that only appear once in the movie. Not to be confused with de-duplicated frames. For
instance, hashes AABCDDE de-duplicated would be ABCDE, but hashes that only appear once are BCE. This distinction is
important since if the same frame appeared multiple times in one edition, we wouldn't know how to match it with the same
frame in a different edition.

We can see that the majority of frames are unique in both editions.

| Unique Theatrical Frames | Percentage Unique Theatrical | Unique Extended Frames | Percentage Unique Extended |
|:-------------------------|:-----------------------------|:-----------------------|:---------------------------|
| 257,199                  | 99.65%                       | 336,314                | 99.31%                     |

### Unique Common Frames

Using the definition of unique frames above, we can match frames between editions to find which are common to both.
We know from a table above that the maximum possible common frames in the extended edition is 76.74%, since that is
the difference in lengths of the two editions. If we compare that to the 10.32% of actually common frames here, then we
potentially have up to 66.42% visually identical frames which are not pixel perfect.

Bear in mind that the maximum possible common frames in the theatrical edition is 100%, which would be the case if the
extended edition contained all the content that exists in the theatrical edition.

| Unique Common Frames | Percentage Unique Common Theatrical | Percentage Unique Common Extended |
|:---------------------|:------------------------------------|:----------------------------------|
| 34,947               | 13.54%                              | 10.32%                            |

### Minute-by-Minute Comparison

Since there is such a large difference between possible common frames and actual common frames, it could be that only
a few scenes are entirely identical, leaving most other scenes to be completely non-identical. Again, I was surprised
that this was not the case.

16 minutes are not included in the table for having no common frames. However, that means that there are 164 minutes
which have at least 1 common frame, and so the majority of scenes have common frames.

<details>
  <summary>Expand for the full results per minute.</summary>

| Count Common per Theatrical Minute | Percentage Common per Theatrical Minute | Theatrical Minute | Extended Minute |
|:-----------------------------------|:----------------------------------------|:------------------|:----------------|
| 510                                | 35.42%                                  | 00:00:00          | 00:00:00        |
| 167                                | 11.60%                                  | 00:01:00          | 00:01:00        |
| 639                                | 44.38%                                  | 00:02:00          | 00:02:00        |
| 278                                | 19.31%                                  | 00:03:00          | 00:03:00        |
| 9                                  | 0.63%                                   | 00:04:00          | 00:06:00        |
| 1                                  | 0.07%                                   | 00:05:00          | 00:07:00        |
| 51                                 | 3.54%                                   | 00:06:00          | 00:09:00        |
| 484                                | 33.61%                                  | 00:07:00          | 00:09:00        |
| 36                                 | 2.50%                                   | 00:08:00          | 00:10:00        |
| 1                                  | 0.07%                                   | 00:10:00          | 00:13:00        |
| 4                                  | 0.28%                                   | 00:11:00          | 00:13:00        |
| 138                                | 9.58%                                   | 00:12:00          | 00:16:00        |
| 110                                | 7.64%                                   | 00:13:00          | 00:18:00        |
| 360                                | 25.00%                                  | 00:14:00          | 00:19:00        |
| 265                                | 18.40%                                  | 00:15:00          | 00:19:00        |
| 71                                 | 4.93%                                   | 00:16:00          | 00:21:00        |
| 144                                | 10.00%                                  | 00:17:00          | 00:22:00        |
| 72                                 | 5.00%                                   | 00:18:00          | 00:24:00        |
| 153                                | 10.63%                                  | 00:19:00          | 00:25:00        |
| 205                                | 14.24%                                  | 00:20:00          | 00:27:00        |
| 70                                 | 4.86%                                   | 00:21:00          | 00:28:00        |
| 79                                 | 5.49%                                   | 00:22:00          | 00:29:00        |
| 81                                 | 5.63%                                   | 00:23:00          | 00:30:00        |
| 315                                | 21.88%                                  | 00:24:00          | 00:31:00        |
| 82                                 | 5.69%                                   | 00:25:00          | 00:32:00        |
| 286                                | 19.86%                                  | 00:27:00          | 00:34:00        |
| 156                                | 10.83%                                  | 00:28:00          | 00:35:00        |
| 466                                | 32.36%                                  | 00:29:00          | 00:36:00        |
| 59                                 | 4.10%                                   | 00:30:00          | 00:37:00        |
| 99                                 | 6.88%                                   | 00:31:00          | 00:38:00        |
| 40                                 | 2.78%                                   | 00:32:00          | 00:40:00        |
| 407                                | 28.26%                                  | 00:33:00          | 00:40:00        |
| 342                                | 23.75%                                  | 00:34:00          | 00:41:00        |
| 798                                | 55.42%                                  | 00:35:00          | 00:42:00        |
| 779                                | 54.10%                                  | 00:36:00          | 00:45:00        |
| 508                                | 35.28%                                  | 00:37:00          | 00:47:00        |
| 192                                | 13.33%                                  | 00:38:00          | 00:47:00        |
| 203                                | 14.10%                                  | 00:39:00          | 00:48:00        |
| 640                                | 44.44%                                  | 00:40:00          | 00:49:00        |
| 262                                | 18.19%                                  | 00:41:00          | 00:50:00        |
| 48                                 | 3.33%                                   | 00:42:00          | 00:51:00        |
| 437                                | 30.35%                                  | 00:43:00          | 00:53:00        |
| 1350                               | 93.75%                                  | 00:44:00          | 00:53:00        |
| 529                                | 36.74%                                  | 00:45:00          | 00:55:00        |
| 84                                 | 5.83%                                   | 00:46:00          | 00:58:00        |
| 216                                | 15.00%                                  | 00:47:00          | 01:03:00        |
| 150                                | 10.42%                                  | 00:48:00          | 01:03:00        |
| 69                                 | 4.79%                                   | 00:49:00          | 01:04:00        |
| 137                                | 9.51%                                   | 00:51:00          | 01:06:00        |
| 67                                 | 4.65%                                   | 00:52:00          | 01:07:00        |
| 313                                | 21.74%                                  | 00:53:00          | 01:12:00        |
| 143                                | 9.93%                                   | 00:54:00          | 01:13:00        |
| 345                                | 23.96%                                  | 00:55:00          | 01:15:00        |
| 234                                | 16.25%                                  | 00:56:00          | 01:15:00        |
| 42                                 | 2.92%                                   | 00:57:00          | 01:16:00        |
| 104                                | 7.22%                                   | 00:58:00          | 01:18:00        |
| 194                                | 13.47%                                  | 00:59:00          | 01:18:00        |
| 118                                | 8.19%                                   | 01:00:00          | 01:19:00        |
| 97                                 | 6.74%                                   | 01:01:00          | 01:21:00        |
| 255                                | 17.71%                                  | 01:02:00          | 01:21:00        |
| 67                                 | 4.65%                                   | 01:03:00          | 01:22:00        |
| 901                                | 62.57%                                  | 01:04:00          | 01:24:00        |
| 1396                               | 96.94%                                  | 01:05:00          | 01:26:00        |
| 238                                | 16.53%                                  | 01:06:00          | 01:27:00        |
| 70                                 | 4.86%                                   | 01:07:00          | 01:28:00        |
| 309                                | 21.46%                                  | 01:08:00          | 01:29:00        |
| 125                                | 8.68%                                   | 01:09:00          | 01:34:00        |
| 79                                 | 5.49%                                   | 01:10:00          | 01:35:00        |
| 7                                  | 0.49%                                   | 01:11:00          | 01:36:00        |
| 1                                  | 0.07%                                   | 01:12:00          | 01:37:00        |
| 65                                 | 4.51%                                   | 01:13:00          | 01:38:00        |
| 392                                | 27.22%                                  | 01:14:00          | 01:39:00        |
| 656                                | 45.56%                                  | 01:15:00          | 01:40:00        |
| 69                                 | 4.79%                                   | 01:16:00          | 01:41:00        |
| 20                                 | 1.39%                                   | 01:17:00          | 01:42:00        |
| 3                                  | 0.21%                                   | 01:18:00          | 01:43:00        |
| 113                                | 7.85%                                   | 01:19:00          | 01:44:00        |
| 240                                | 16.67%                                  | 01:20:00          | 01:45:00        |
| 88                                 | 6.11%                                   | 01:21:00          | 01:50:00        |
| 1279                               | 88.82%                                  | 01:22:00          | 01:50:00        |
| 1264                               | 87.78%                                  | 01:23:00          | 01:51:00        |
| 584                                | 40.56%                                  | 01:24:00          | 01:52:00        |
| 278                                | 19.31%                                  | 01:25:00          | 01:54:00        |
| 10                                 | 0.69%                                   | 01:26:00          | 01:55:00        |
| 113                                | 7.85%                                   | 01:27:00          | 01:55:00        |
| 149                                | 10.35%                                  | 01:28:00          | 01:57:00        |
| 65                                 | 4.51%                                   | 01:29:00          | 01:58:00        |
| 34                                 | 2.36%                                   | 01:30:00          | 01:59:00        |
| 218                                | 15.14%                                  | 01:31:00          | 01:59:00        |
| 60                                 | 4.17%                                   | 01:32:00          | 02:00:00        |
| 19                                 | 1.32%                                   | 01:33:00          | 02:01:00        |
| 99                                 | 6.88%                                   | 01:34:00          | 02:03:00        |
| 251                                | 17.43%                                  | 01:35:00          | 02:04:00        |
| 578                                | 40.14%                                  | 01:37:00          | 02:06:00        |
| 1417                               | 98.40%                                  | 01:38:00          | 02:07:00        |
| 50                                 | 3.47%                                   | 01:39:00          | 02:08:00        |
| 232                                | 16.11%                                  | 01:40:00          | 02:09:00        |
| 93                                 | 6.46%                                   | 01:41:00          | 02:10:00        |
| 19                                 | 1.32%                                   | 01:42:00          | 02:11:00        |
| 825                                | 57.29%                                  | 01:44:00          | 02:13:00        |
| 326                                | 22.64%                                  | 01:45:00          | 02:14:00        |
| 1                                  | 0.07%                                   | 01:46:00          | 02:15:00        |
| 17                                 | 1.18%                                   | 01:47:00          | 02:16:00        |
| 88                                 | 6.11%                                   | 01:48:00          | 02:23:00        |
| 232                                | 16.11%                                  | 01:49:00          | 02:23:00        |
| 1                                  | 0.07%                                   | 01:50:00          | 02:24:00        |
| 187                                | 12.99%                                  | 01:51:00          | 02:25:00        |
| 462                                | 32.08%                                  | 01:52:00          | 02:26:00        |
| 4                                  | 0.28%                                   | 01:53:00          | 02:28:00        |
| 103                                | 7.15%                                   | 01:54:00          | 02:28:00        |
| 156                                | 10.83%                                  | 01:55:00          | 02:29:00        |
| 6                                  | 0.42%                                   | 01:56:00          | 02:30:00        |
| 217                                | 15.07%                                  | 01:57:00          | 02:31:00        |
| 23                                 | 1.60%                                   | 01:58:00          | 02:32:00        |
| 1                                  | 0.07%                                   | 01:59:00          | 02:33:00        |
| 1                                  | 0.07%                                   | 02:00:00          | 02:34:00        |
| 393                                | 27.29%                                  | 02:01:00          | 02:35:00        |
| 142                                | 9.86%                                   | 02:02:00          | 02:38:00        |
| 54                                 | 3.75%                                   | 02:03:00          | 02:39:00        |
| 65                                 | 4.51%                                   | 02:04:00          | 02:40:00        |
| 6                                  | 0.42%                                   | 02:05:00          | 02:41:00        |
| 39                                 | 2.71%                                   | 02:06:00          | 02:43:00        |
| 37                                 | 2.57%                                   | 02:07:00          | 02:44:00        |
| 6                                  | 0.42%                                   | 02:08:00          | 02:44:00        |
| 10                                 | 0.69%                                   | 02:10:00          | 02:46:00        |
| 2                                  | 0.14%                                   | 02:11:00          | 02:47:00        |
| 109                                | 7.57%                                   | 02:12:00          | 02:48:00        |
| 23                                 | 1.60%                                   | 02:13:00          | 02:49:00        |
| 97                                 | 6.74%                                   | 02:14:00          | 02:50:00        |
| 114                                | 7.92%                                   | 02:15:00          | 02:51:00        |
| 29                                 | 2.01%                                   | 02:16:00          | 02:53:00        |
| 20                                 | 1.39%                                   | 02:17:00          | 02:53:00        |
| 93                                 | 6.46%                                   | 02:18:00          | 02:54:00        |
| 167                                | 11.60%                                  | 02:19:00          | 02:55:00        |
| 13                                 | 0.90%                                   | 02:20:00          | 02:57:00        |
| 120                                | 8.33%                                   | 02:21:00          | 02:57:00        |
| 30                                 | 2.08%                                   | 02:23:00          | 02:59:00        |
| 18                                 | 1.25%                                   | 02:24:00          | 03:01:00        |
| 15                                 | 1.04%                                   | 02:25:00          | 03:01:00        |
| 10                                 | 0.69%                                   | 02:26:00          | 03:02:00        |
| 3                                  | 0.21%                                   | 02:27:00          | 03:04:00        |
| 46                                 | 3.19%                                   | 02:28:00          | 03:04:00        |
| 794                                | 55.14%                                  | 02:29:00          | 03:05:00        |
| 930                                | 64.58%                                  | 02:30:00          | 03:06:00        |
| 785                                | 54.51%                                  | 02:31:00          | 03:07:00        |
| 94                                 | 6.53%                                   | 02:32:00          | 03:09:00        |
| 173                                | 12.01%                                  | 02:33:00          | 03:10:00        |
| 288                                | 20.00%                                  | 02:34:00          | 03:11:00        |
| 39                                 | 2.71%                                   | 02:35:00          | 03:12:00        |
| 74                                 | 5.14%                                   | 02:36:00          | 03:13:00        |
| 3                                  | 0.21%                                   | 02:37:00          | 03:14:00        |
| 210                                | 14.58%                                  | 02:38:00          | 03:15:00        |
| 372                                | 25.83%                                  | 02:39:00          | 03:16:00        |
| 114                                | 7.92%                                   | 02:40:00          | 03:17:00        |
| 3                                  | 0.21%                                   | 02:42:00          | 03:19:00        |
| 49                                 | 3.40%                                   | 02:43:00          | 03:20:00        |
| 30                                 | 2.08%                                   | 02:44:00          | 03:21:00        |
| 176                                | 12.22%                                  | 02:45:00          | 03:22:00        |
| 15                                 | 1.04%                                   | 02:47:00          | 03:24:00        |
| 57                                 | 3.96%                                   | 02:48:00          | 03:31:00        |
| 51                                 | 3.54%                                   | 02:49:00          | 03:33:00        |
| 127                                | 8.82%                                   | 02:50:00          | 03:33:00        |
| 106                                | 7.36%                                   | 02:51:00          | 03:34:00        |
| 1                                  | 0.07%                                   | 02:59:00          | 03:55:00        |

</details>

Alternatively, I have grouped the results into buckets of 10%, each bucket shows how similar each minute of the
theatrical edition is to the extended edition. For example, there are 97 minutes of the theatrical edition that have
between 0%-10% similarity with the respective minute of the extended edition. On the other hand, there are only 3
minutes of the theatrical edition that have between 90%-100% similarity.

| Bucket     | Count |
|:-----------|:------|
| = 00%      | 16    |
| 00% - 10%  | 97    |
| 10% - 20%  | 31    |
| 20% - 30%  | 12    |
| 30% - 40%  | 7     |
| 40% - 50%  | 5     |
| 50% - 60%  | 5     |
| 60% - 70%  | 2     |
| 70% - 80%  | 0     |
| 80% - 90%  | 2     |
| 90% - 100% | 3     |
| = 100%     | 0     |

### Conclusion

Since most minutes contain at least one identical frame, we can be confident in using the MD5 hashes as anchors when
finding the exact differences between editions. However, given the low percentage of common frames, we must also turn
to imperfect image hashing algorithms to match visually identical frames.

## Visually Identical Frames

We can compare similar queries to those performed on MD5 above, but on the results of the various image hashing
algorithms. MD5 understandably returns the lowest common unique frames, and is similar to the Marr Hildreth algorithm.
The Block Mean hash returns the highest common unique frames. Though if we calculate the union of all the returned
frames from all the algorithms, we can unique match over 82% of the theatrical edition, which is over 26% more than
any single algorithm alone.

| algorithm        | count   | percentage\_theatrical | percentage\_extended |
|:-----------------|:--------|:-----------------------|:---------------------|
| union\_all       | 212,803 | 82.45%                 | 62.84%               |
| block\_mean      | 144,546 | 56.00%                 | 42.68%               |
| perceptual       | 138,648 | 53.72%                 | 40.94%               |
| average          | 133,522 | 51.73%                 | 39.43%               |
| radial\_variance | 60,643  | 23.50%                 | 17.91%               |
| marr\_hildreth   | 34,959  | 13.54%                 | 10.32%               |
| md5              | 34,947  | 13.54%                 | 10.32%               |

### Validity of Matches

However, now that we're matching imperfectly, we need to be careful that our matches are valid. For example, we should
consider ordering of frame indexes to ensure that the extended frame index always increases as the theatrical frame
index increases. There may exist other invalid criteria, but this one is easy to look for.

If we take frames ABC from the theatrical edition, and frames XYZ from the extended edition, matches of AX BY CZ are
all of consecutive frames. But matches of AY BZ CX are out of order, and therefore probably invalid. That is assuming
visually identical frames from different editions cannot exist out of order, which may be an incorrect depending on how
the editions are spliced together.

| algorithm        | invalid\_count | percentage\_invalid |
|:-----------------|:---------------|:--------------------|
| union\_all       | 387            | 0.15%               |
| average          | 336            | 0.13%               |
| perceptual       | 181            | 0.07%               |
| block\_mean      | 45             | 0.02%               |
| radial\_variance | 8              | 0.00%               |
| marr\_hildreth   | 0              | 0.00%               |
| md5              | 0              | 0.00%               |

The Block Mean hash stands out when you consider it provides the most common unique frames, as well as having a
relatively low count of invalid ordering, compared to other algorithms. Though, the percentages are all low, so we won't
lose many matches if we exclude any index that appears in these invalid results.

| Algorithm  | Count Unvalidated | Count Validated | Percentage Validated Theatrical | Percentage Validated Extended |
|:-----------|:------------------|:----------------|:--------------------------------|:------------------------------|
| union\_all | 212,803           | 211,971         | 82.13%                          | 62.59%                        |

## Missing Ranges

Given we can now match at least 82% of theatrical frames, we can quickly estimate where the differences are. If we group
by minute we can see 11 ranges in the extended edition that do not appear in the theatrical edition. Note that these
ranges only include full minutes which have no matches, so we can be quite certain that they correspond to long extended
scenes.

| range\_start | range\_end | duration | range\_start\_time | range\_end\_time | duration\_time |
|:-------------|:-----------|:---------|:-------------------|:-----------------|:---------------|
| 5            | 5          | 1        | 00:05:00           | 00:05:00         | 00:01:00       |
| 43           | 43         | 1        | 00:43:00           | 00:43:00         | 00:01:00       |
| 56           | 56         | 1        | 00:56:00           | 00:56:00         | 00:01:00       |
| 59           | 61         | 3        | 00:59:00           | 01:01:00         | 00:03:00       |
| 69           | 70         | 2        | 01:09:00           | 01:10:00         | 00:02:00       |
| 91           | 92         | 2        | 01:31:00           | 01:32:00         | 00:02:00       |
| 108          | 108        | 1        | 01:48:00           | 01:48:00         | 00:01:00       |
| 139          | 141        | 3        | 02:19:00           | 02:21:00         | 00:03:00       |
| 206          | 209        | 4        | 03:26:00           | 03:29:00         | 00:04:00       |
| 215          | 215        | 1        | 03:35:00           | 03:35:00         | 00:01:00       |
| 225          | 234        | 10       | 03:45:00           | 03:54:00         | 00:10:00       |

If we want more granularity we can perform the same query, but by second instead of by minute. This results in a far
larger dataset, with lower certainty of corresponding to extended scenes, but with higher precision. For example, the
first scene detected using minutes is between 5:00-6:00, but the same scene using seconds is 04:09-06:09.

<details>
  <summary>Expand for the full ranges by second.</summary>

| range\_start | range\_end | duration | range\_start\_time | range\_end\_time | duration\_time |
|:-------------|:-----------|:---------|:-------------------|:-----------------|:---------------|
| 0            | 1          | 2        | 00:00:00           | 00:00:01         | 00:00:02       |
| 17           | 17         | 1        | 00:00:17           | 00:00:17         | 00:00:01       |
| 24           | 24         | 1        | 00:00:24           | 00:00:24         | 00:00:01       |
| 31           | 32         | 2        | 00:00:31           | 00:00:32         | 00:00:02       |
| 249          | 369        | 121      | 00:04:09           | 00:06:09         | 00:02:01       |
| 371          | 376        | 6        | 00:06:11           | 00:06:16         | 00:00:06       |
| 486          | 505        | 20       | 00:08:06           | 00:08:25         | 00:00:20       |
| 821          | 824        | 4        | 00:13:41           | 00:13:44         | 00:00:04       |
| 828          | 862        | 35       | 00:13:48           | 00:14:22         | 00:00:35       |
| 866          | 883        | 18       | 00:14:26           | 00:14:43         | 00:00:18       |
| 901          | 1000       | 100      | 00:15:01           | 00:16:40         | 00:01:40       |
| 1008         | 1008       | 1        | 00:16:48           | 00:16:48         | 00:00:01       |
| 1249         | 1294       | 46       | 00:20:49           | 00:21:34         | 00:00:46       |
| 1383         | 1438       | 56       | 00:23:03           | 00:23:58         | 00:00:56       |
| 1443         | 1446       | 4        | 00:24:03           | 00:24:06         | 00:00:04       |
| 1603         | 1617       | 15       | 00:26:43           | 00:26:57         | 00:00:15       |
| 1620         | 1622       | 3        | 00:27:00           | 00:27:02         | 00:00:03       |
| 1783         | 1815       | 33       | 00:29:43           | 00:30:15         | 00:00:33       |
| 1823         | 1824       | 2        | 00:30:23           | 00:30:24         | 00:00:02       |
| 2573         | 2694       | 122      | 00:42:53           | 00:44:54         | 00:02:02       |
| 3101         | 3120       | 20       | 00:51:41           | 00:52:00         | 00:00:20       |
| 3210         | 3211       | 2        | 00:53:30           | 00:53:31         | 00:00:02       |
| 3216         | 3223       | 8        | 00:53:36           | 00:53:43         | 00:00:08       |
| 3342         | 3424       | 83       | 00:55:42           | 00:57:04         | 00:01:23       |
| 3496         | 3528       | 33       | 00:58:16           | 00:58:48         | 00:00:33       |
| 3540         | 3763       | 224      | 00:59:00           | 01:02:43         | 00:03:44       |
| 4082         | 4274       | 193      | 01:08:02           | 01:11:14         | 00:03:13       |
| 4280         | 4280       | 1        | 01:11:20           | 01:11:20         | 00:00:01       |
| 4282         | 4289       | 8        | 01:11:22           | 01:11:29         | 00:00:08       |
| 4294         | 4356       | 63       | 01:11:34           | 01:12:36         | 00:01:03       |
| 5005         | 5010       | 6        | 01:23:25           | 01:23:30         | 00:00:06       |
| 5053         | 5135       | 83       | 01:24:13           | 01:25:35         | 00:01:23       |
| 5440         | 5635       | 196      | 01:30:40           | 01:33:55         | 00:03:16       |
| 5641         | 5664       | 24       | 01:34:01           | 01:34:24         | 00:00:24       |
| 5760         | 5765       | 6        | 01:36:00           | 01:36:05         | 00:00:06       |
| 6326         | 6385       | 60       | 01:45:26           | 01:46:25         | 00:01:00       |
| 6432         | 6440       | 9        | 01:47:12           | 01:47:20         | 00:00:09       |
| 6444         | 6456       | 13       | 01:47:24           | 01:47:36         | 00:00:13       |
| 6462         | 6579       | 118      | 01:47:42           | 01:49:39         | 00:01:58       |
| 6605         | 6607       | 3        | 01:50:05           | 01:50:07         | 00:00:03       |
| 6786         | 6821       | 36       | 01:53:06           | 01:53:41         | 00:00:36       |
| 6834         | 6836       | 3        | 01:53:54           | 01:53:56         | 00:00:03       |
| 6843         | 6843       | 1        | 01:54:03           | 01:54:03         | 00:00:01       |
| 6846         | 6855       | 10       | 01:54:06           | 01:54:15         | 00:00:10       |
| 7351         | 7362       | 12       | 02:02:31           | 02:02:42         | 00:00:12       |
| 8229         | 8252       | 24       | 02:17:09           | 02:17:32         | 00:00:24       |
| 8259         | 8293       | 35       | 02:17:39           | 02:18:13         | 00:00:35       |
| 8302         | 8573       | 272      | 02:18:22           | 02:22:53         | 00:04:32       |
| 8757         | 8770       | 14       | 02:25:57           | 02:26:10         | 00:00:14       |
| 9438         | 9500       | 63       | 02:37:18           | 02:38:20         | 00:01:03       |
| 9511         | 9514       | 4        | 02:38:31           | 02:38:34         | 00:00:04       |
| 9730         | 9730       | 1        | 02:42:10           | 02:42:10         | 00:00:01       |
| 9732         | 9770       | 39       | 02:42:12           | 02:42:50         | 00:00:39       |
| 10012        | 10012      | 1        | 02:46:52           | 02:46:52         | 00:00:01       |
| 10315        | 10321      | 7        | 02:51:55           | 02:52:01         | 00:00:07       |
| 10372        | 10372      | 1        | 02:52:52           | 02:52:52         | 00:00:01       |
| 10387        | 10387      | 1        | 02:53:07           | 02:53:07         | 00:00:01       |
| 10437        | 10438      | 2        | 02:53:57           | 02:53:58         | 00:00:02       |
| 10902        | 10904      | 3        | 03:01:42           | 03:01:44         | 00:00:03       |
| 11314        | 11314      | 1        | 03:08:34           | 03:08:34         | 00:00:01       |
| 11316        | 11316      | 1        | 03:08:36           | 03:08:36         | 00:00:01       |
| 11318        | 11318      | 1        | 03:08:38           | 03:08:38         | 00:00:01       |
| 11321        | 11336      | 16       | 03:08:41           | 03:08:56         | 00:00:16       |
| 12137        | 12137      | 1        | 03:22:17           | 03:22:17         | 00:00:01       |
| 12140        | 12140      | 1        | 03:22:20           | 03:22:20         | 00:00:01       |
| 12270        | 12310      | 41       | 03:24:30           | 03:25:10         | 00:00:41       |
| 12319        | 12631      | 313      | 03:25:19           | 03:30:31         | 00:05:13       |
| 12876        | 12999      | 124      | 03:34:36           | 03:36:39         | 00:02:04       |
| 13001        | 13066      | 66       | 03:36:41           | 03:37:46         | 00:01:06       |
| 13068        | 13086      | 19       | 03:37:48           | 03:38:06         | 00:00:19       |
| 13088        | 13094      | 7        | 03:38:08           | 03:38:14         | 00:00:07       |
| 13096        | 13096      | 1        | 03:38:16           | 03:38:16         | 00:00:01       |
| 13098        | 13159      | 62       | 03:38:18           | 03:39:19         | 00:01:02       |
| 13161        | 13163      | 3        | 03:39:21           | 03:39:23         | 00:00:03       |
| 13166        | 13170      | 5        | 03:39:26           | 03:39:30         | 00:00:05       |
| 13172        | 13175      | 4        | 03:39:32           | 03:39:35         | 00:00:04       |
| 13177        | 13180      | 4        | 03:39:37           | 03:39:40         | 00:00:04       |
| 13182        | 13185      | 4        | 03:39:42           | 03:39:45         | 00:00:04       |
| 13187        | 13191      | 5        | 03:39:47           | 03:39:51         | 00:00:05       |
| 13193        | 13195      | 3        | 03:39:53           | 03:39:55         | 00:00:03       |
| 13197        | 13201      | 5        | 03:39:57           | 03:40:01         | 00:00:05       |
| 13204        | 13204      | 1        | 03:40:04           | 03:40:04         | 00:00:01       |
| 13206        | 13207      | 2        | 03:40:06           | 03:40:07         | 00:00:02       |
| 13209        | 13215      | 7        | 03:40:09           | 03:40:15         | 00:00:07       |
| 13217        | 13217      | 1        | 03:40:17           | 03:40:17         | 00:00:01       |
| 13221        | 13230      | 10       | 03:40:21           | 03:40:30         | 00:00:10       |
| 13233        | 13260      | 28       | 03:40:33           | 03:41:00         | 00:00:28       |
| 13262        | 13273      | 12       | 03:41:02           | 03:41:13         | 00:00:12       |
| 13275        | 13281      | 7        | 03:41:15           | 03:41:21         | 00:00:07       |
| 13284        | 13311      | 28       | 03:41:24           | 03:41:51         | 00:00:28       |
| 13313        | 13315      | 3        | 03:41:53           | 03:41:55         | 00:00:03       |
| 13317        | 13321      | 5        | 03:41:57           | 03:42:01         | 00:00:05       |
| 13323        | 13327      | 5        | 03:42:03           | 03:42:07         | 00:00:05       |
| 13329        | 13340      | 12       | 03:42:09           | 03:42:20         | 00:00:12       |
| 13342        | 13343      | 2        | 03:42:22           | 03:42:23         | 00:00:02       |
| 13345        | 13346      | 2        | 03:42:25           | 03:42:26         | 00:00:02       |
| 13348        | 13349      | 2        | 03:42:28           | 03:42:29         | 00:00:02       |
| 13351        | 13362      | 12       | 03:42:31           | 03:42:42         | 00:00:12       |
| 13364        | 13383      | 20       | 03:42:44           | 03:43:03         | 00:00:20       |
| 13385        | 13398      | 14       | 03:43:05           | 03:43:18         | 00:00:14       |
| 13400        | 13410      | 11       | 03:43:20           | 03:43:30         | 00:00:11       |
| 13412        | 13478      | 67       | 03:43:32           | 03:44:38         | 00:01:07       |
| 13480        | 14100      | 621      | 03:44:40           | 03:55:00         | 00:10:21       |
| 14102        | 14102      | 1        | 03:55:02           | 03:55:02         | 00:00:01       |
| 14104        | 14104      | 1        | 03:55:04           | 03:55:04         | 00:00:01       |

</details>