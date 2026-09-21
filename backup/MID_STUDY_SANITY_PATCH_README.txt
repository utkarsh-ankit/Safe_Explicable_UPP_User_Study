MID STUDY SANITY PATCH

This patch changes the flow to:

Participant page
Consent
Instructions
First route task
Mid study attention check
Second route task
Survey
Completion

Files changed:

app.py
study/database.py
templates/login.html
templates/instructions.html
templates/sanity.html
templates/sanity_failed.html
tests/test_sanity.py

The patch does not contain study/domains.py, study/scoring.py, the database file, or any map files. Your current layouts and reward settings will not be replaced.

Failure behavior:

The attention check has one attempt. On failure, all rows for that participant are deleted from the trials and surveys tables. The participant row and sanity_checks row remain so the failed check can be audited. The participant is shown a completion code, but their route data is not retained for research analysis.

PythonAnywhere installation:

1. Back up data/study.sqlite3.
2. Upload the patch ZIP to /home/sepupp1userstudy/.
3. Open a Bash console.
4. Run:

cd /home/sepupp1userstudy/sep_upp_user_study
cp data/study.sqlite3 data/study_backup_before_mid_sanity.sqlite3
unzip -o /home/sepupp1userstudy/sep_upp_mid_study_sanity_patch.zip

5. Open the Web page and press Reload.
6. Use a new participant identifier for testing.

Before recruitment, replace the approximate duration, privacy text, consent text, and researcher contact information with the wording approved for your study.
