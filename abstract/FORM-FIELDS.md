# SSAC 2027 abstract submission: form fields

Deadline as published by the conference: **2026-10-01, 23:59 EST**. This project works to
**05:59 Madrid on 2026-10-02**, which is the earlier of the two readings. Both readings are
recorded in `docs/runbook.md`. The planned submission time is 12:00 Madrid on 2026-10-01, a
full clock day before the earlier reading.

This file is an owner step. It is on the critical path for SOP step W6.1, and no agent can
do it. An unauthenticated fetch of the form returns HTTP 401 with a redirect to
`accounts.google`, so the field list below is inferred from the conference page, not read
off the form. Open the form, fill the blanks in section 3, correct anything that is wrong,
and commit the file.

Budget: about 20 minutes. Do not submit anything while filling this in. Section 3 is a
survey of the form, not a submission.

Handling note. This file names the submitting account. Decision D-69 keeps author
information out of every file reachable from the repository root while the SSAC review
window is open. That scan covers `README.md`, `LICENSE`, `CITATION.cff`, `docs/`, `app/`,
`.github/` and any file they link to. Do not link this file from any of them.

Numbers in this file. Every numeric literal below is a form constraint, an owner budget, a
date or an observed HTTP fact. None of them is a model output, so none can come from
`docs/numbers.json`. Each is listed with its justification in `docs/numbers-allow.txt`,
which is one of the three sources `quality/check_numbers.py` reads. If the form contradicts
one of them, correct it in section 4 and change the justification there in the same commit.

---

## 1. Getting to the form

Redirect chain, verified 2026-09-22:

    https://bit.ly/4xIaYy9
      -> 301 -> https://forms.gle/cN4HZVkJdQ13cNL98
      -> 302 -> https://docs.google.com/forms/d/e/1FAIpQLSfS8q4v839ea_sdyox9t6iq-tJ7mTUleo___7BY2lmZ2s83eg/viewform

`curl -L` without a session returns **HTTP 401, 9,251 bytes**. That is expected and is not a
broken link.

Sign in first, as **hudpag@gmail.com**, then open the last URL in the chain. If the form
shows a different account in the top right, switch accounts before filling anything in.

Confirm and record here:

- [ ] Signed in as hudpag@gmail.com: yes / no
- [ ] Form opened and readable: yes / no
- [ ] Form title as shown on the page: `________________________`
- [ ] Date and Madrid time this survey was done: `________________________`

---

## 2. Conference requirements, verified from sloansportsconference.com on 2026-09-22

These are the constraints the abstract is written against. If the form contradicts any of
them, the form wins. Write the correction into section 4 and it will be carried into
`DEVIATIONS.md`.

- Length: "fewer than 500 words, including title and body". The project drafts to a ceiling
  of 470 words.
- Exhibits: "up to two tables or figures combined". One table and one figure is the planned
  maximum, and the figure is first on the cut ladder if space is short.
- Four required sections: **Introduction, Methods, Results, Conclusion**.
- Results must be "actual (not promised) results along with relevant statistics".
- Review is blind.
- Tracks include Baseball.
- Judging criteria: novelty, academic rigor and validity, reproducibility, application,
  interest and impact.
- The repository-link requirement applies to **papers**, not abstracts. Do not paste a
  repository link into the abstract body.
- Abstract due 2026-10-01, 23:59 EST. Full paper due 2026-12-04, 23:59.
- Finalist, poster and conference dates are not on that page and are not carried as
  verified. If the form states any of them, record them in section 4.

---

## 3. Fields to survey

Fill in the blank after each field. If a field does not exist on the form, write "absent".
If a field exists that is not listed here, add it to section 4.

1. **Title.** Required by the conference wording, since the word count includes the title.
   - Field label on the form: `________________________`
   - Input type (short text / long text / other): `________________`
   - Character or word cap shown: `________________`
   - Whether the title is counted separately from the body, or entered inside the body field:
     `________________`

2. **Track.** The answer is **Baseball**.
   - Field label: `________________________`
   - Exact option text to select: `________________________`
   - Full list of options offered: `________________________`

3. **Abstract body.** Under 500 words including the title.
   - Field label: `________________________`
   - Character cap enforced by the form, if any: `________________`
   - Whether the field accepts line breaks and blank lines: `________________`
   - Whether it accepts any formatting (bold, headings, markdown), or is plain text only:
     `________________`
   - Whether it strips leading or trailing whitespace: `________________`

4. **The four required sections.** Introduction, Methods, Results, Conclusion.
   - Whether they are four separate fields, or four headings inside one body field:
     `________________________`
   - If separate, record each label and each cap:
     - Introduction: `________________`
     - Methods: `________________`
     - Results: `________________`
     - Conclusion: `________________`
   - Whether the form states anywhere that Results must be actual rather than promised:
     `________________`

5. **Tables and figures.** Up to two combined.
   - Whether there is an upload field at all: `________________`
   - Accepted file types: `________________`
   - Size cap: `________________`
   - Maximum number of files: `________________`
   - If there is no upload field, the table goes into the body as plain text, budgeted at
     about 60 words, and the figure is dropped. Record which case applies:
     `________________________`

6. **Blind review and name handling.** Author identity goes in the form only, never in the
   abstract body.
   - Whether the form says anything about blind review or anonymisation: `________________`
   - Whether it asks for author names in a separate section from the abstract:
     `________________`
   - Whether it warns that identifying information in the body disqualifies the entry:
     `________________`
   - Whether it asks for a repository or supplementary link: `________________`
     If yes, record whether it is optional, and do not supply one for the abstract round
     unless the form requires it.

7. **Contact and author details.** Have these ready.
   - Name: Hudson Pagni
   - Affiliation: UCLA
   - Status: undergraduate, class of June 2028
   - Email: hudpag@gmail.com
   - Fields the form actually asks for: `________________________`
   - Whether it asks for co-authors, and how many rows it allows: `________________`
   - Whether it asks for a phone number, a mailing address, or a headshot: `________________`
   - Whether it asks for a resume or a CV: `________________`

8. **Consent, terms and eligibility.**
   - Checkboxes or agreements required: `________________________`
   - Any eligibility question (student status, prior submission, exclusivity):
     `________________________`

9. **Submission mechanics.**
   - Whether a Google sign-in is required to submit: `________________`
   - Whether the form allows editing after submit ("Edit your response"): `________________`
   - Whether it sends a confirmation email to the signed-in account: `________________`
   - Whether there is a "one response per account" restriction: `________________`
   - Number of pages or steps in the form: `________________`
   - Any question that requires an answer the project does not yet have:
     `________________________`

---

## 4. Anything the form says that this file does not

Write it down verbatim, with the date. A surprise found on 1 October is a same-day rewrite,
which is exactly what this survey exists to prevent.

    (nothing recorded yet)

---

## 5. After the survey

1. Commit this file with the blanks filled.
2. If any answer contradicts section 2, append the correction to `DEVIATIONS.md` rather than
   editing the pre-registration in place.
3. If the form has no upload field, tell the abstract step now, so the table is drafted as
   plain text from the start.
4. Submission itself is SOP step W6.12, not this step. That step archives the confirmation
   screenshot, the receipt email and the exact submitted text, then tags the commit.
