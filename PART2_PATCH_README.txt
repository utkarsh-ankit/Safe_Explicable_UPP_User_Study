PART 2 PATCH — attention check moved, image comparison added

New flow:

  Participant page
  Consent
  Instructions
  First route task
  Second route task
  Attention check          <- moved here, was between the two route tasks
  Part 2: compare three routes   <- new
  Survey
  Completion

Files in this patch:

  app.py                             modified
  study/database.py                  modified
  study/comparison.py                new
  templates/compare.html             new
  templates/instructions.html        modified (copy only)
  templates/sanity.html              modified (copy only)
  tests/test_comparison.py           new
  static/images/compare/route_a.png  new
  static/images/compare/route_b.png  new
  static/images/compare/route_c.png  new

The patch does not contain study/domains.py, study/scoring.py, the database
file, or the task map files. Layouts and reward settings are not replaced.

Part 2:

  All participants see the same three partially observable route images,
  regardless of whether they were assigned the full or partial condition for
  the two drawing tasks. The three images are shown together on one page,
  in a random order that is fixed per participant and stored in the database.
  Participants see only "Route 1", "Route 2", "Route 3". Image file names are
  neutral (route_a / route_b / route_c) so the page source does not reveal
  which planner produced which route.

  Server side mapping, in study/comparison.py:

    baseline -> images/compare/route_a.png
    optimal  -> images/compare/route_b.png
    sepupp   -> images/compare/route_c.png

  Each participant gives one 1 to 5 star rating per route and picks one route
  as their forced choice, plus an optional free text reason.

Database:

  A new "comparisons" table is created by init_db using CREATE TABLE IF NOT
  EXISTS, so no manual migration is needed. Existing rows are untouched.
  The CSV export gains comparison_order_json, comparison_choice_slot,
  comparison_choice_policy, comparison_ratings_json,
  comparison_response_time_ms and comparison_explanation.

Failure behaviour:

  The attention check still has one attempt. On failure, the trials,
  comparisons and surveys rows for that participant are deleted and the
  completion code is invalidated. The participant row and the sanity_checks
  row remain for audit.

PythonAnywhere installation:

  1. Back up data/study.sqlite3.
  2. Upload this patch ZIP to /home/sepupp1userstudy/.
  3. Open a Bash console.
  4. Run:

     cd /home/sepupp1userstudy/sep_upp_user_study
     cp data/study.sqlite3 data/study_backup_before_part2.sqlite3
     unzip -o /home/sepupp1userstudy/sep_upp_part2_patch.zip

  5. Open the Web page and press Reload.
  6. Use a new participant identifier for testing, and walk the whole flow
     once to confirm the images load and the ratings save.

Known issue not touched by this patch:

  tests/test_scoring.py fails on two search_recon tests. They assume the
  start cell is (10, 5), but study/domains.py uses (0, 0). This failure
  exists in the current code and is unrelated to this patch.
