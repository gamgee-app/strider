# Movie Edition Comparer

A simple python package for finding common and unique scenes in various editions of the same movie.
- Calculate the hashes of each video frame, using various different image hashing algorithms
- Store those hashes in a database, so as not to require rehashing with updates to the comparison logic
- Compare the hashes, returning any differences found
