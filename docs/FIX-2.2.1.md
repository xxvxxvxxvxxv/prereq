# PREREQ 2.2.1: independent course retrieval

Scope: a local patch to PREREQ only. No account access or publication.

## Reproduced defect in 2.2.0

Both graph_index and the course loader depended on a successfully parsed full
semester catalog. A timeout or parse failure in one all-subject request blocked
all prerequisite requests. The degree endpoint could still show Degree checked,
which verified only major/admission category data, not prerequisites.

## Repair

- The index starts this major's course-detail checks without the aggregate catalog.
- An existing checked aggregate is reused when available, but never required.
- Without a cached link, an exact single-course POST preserves the captured
  Banner form shape, repeated parameters and empty values. The returned link
  must match the selected course and catalog term before its detail is read.
- Every configured major uses this path. Required courses are fetched first,
  then university and electives. Visual section order is unchanged.
- Successful term/course records are shared across majors. Concurrent reads
  are coalesced; another course's or term's record is never substituted.
- The counter identifies the current course. Coverage distinguishes loaded
  pages from parsed rules and retains source error messages.
- Unknown requirements do not create guessed edges. Dynamic Schedule remains
  separate from catalog membership and from cohort requirements.

## Limits

This removes a demonstrated code dependency, not a proven diagnosis of every
possible live Banner failure. A screenshot alone cannot establish whether a
request timed out, is still processing, or failed parsing. The runtime failed
DNS resolution for both Sabanci and the public deployment. Live responses from
this patch are not verified here. No all-major live dataset is claimed.
