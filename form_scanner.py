"""
Read-only application-form scanner. Opens a real live application page in
a real (headless) browser and returns every question the form asks --
field type, required-ness, and (for dropdowns) the real options -- with
NO filling, NO answer lookups, NO submission. Nothing here writes
anything or touches Telegram; it only reads the page.

Directly ported from job-finder/auto-apply/form_filler.py (specifically
the functions scan_fields_only() depends on), after a full day of real
debugging against live Ashby/Greenhouse markup in that repo -- the
label-to-field matching (including the sibling-wrapper fallback for a
label whose `for` points nowhere), the data-field-path fallback for a
field with neither id nor name, and the aria-controls-based dropdown
lookup (works for both react-select AND a custom autocomplete widget,
not just one vendor's ID naming scheme) are all confirmed-working fixes,
not first-pass guesses. If a form scans wrong here, check job-finder's
form_filler.py history before re-deriving any of this from scratch.
"""
from playwright.sync_api import sync_playwright

TIMEOUT_MS = 30000


def _locate_dropdown_options(page, input_loc, field_id: str, max_wait_ms: int = 3000):
    """Finds the real options list for an open combobox dropdown using the
    input's own aria-controls attribute (standard ARIA combobox practice)
    rather than assuming any one vendor's ID naming scheme. Confirmed
    necessary the hard way: react-select uses #react-select-{id}-listbox,
    but a custom-built autocomplete widget (confirmed on Ashby's own
    Location field -- class "ashby-application-form-input-autocomplete",
    NOT react-select's "select__..." classes) renders its popup at a
    React-generated id like ":r0:" that has nothing to do with the field's
    own id/name/field_id at all -- only aria-controls reliably points at
    the right container for either widget. field_id is kept as a fallback
    only, in case some field never sets aria-controls at all.

    Polls rather than a single fixed wait, since options can take a moment
    to populate after typing (a live geocoding-backed field noticeably
    more than a static preset list) -- adapts to whichever is true without
    slowing down the fast, common case."""
    poll_interval_ms = 200
    waited_ms = 0

    def _current_options():
        controls_id = input_loc.get_attribute("aria-controls")
        if controls_id:
            listbox = page.locator(f'[id="{controls_id}"]')
        else:
            listbox = page.locator(f'#react-select-{field_id}-listbox')
        return listbox.locator('[role="option"]')

    options = _current_options()
    count = options.count()
    while count == 0 and waited_ms < max_wait_ms:
        page.wait_for_timeout(poll_interval_ms)
        waited_ms += poll_interval_ms
        options = _current_options()  # aria-controls may not be set until the dropdown actually opens
        count = options.count()
    return options


def _peek_react_select_options(page, input_loc, field_id: str) -> list:
    """Opens a combobox dropdown just to read its available options --
    without selecting anything -- so an escalation can show you the real
    choices instead of asking blind. Closes the dropdown before returning."""
    try:
        input_loc.click()
        page.wait_for_timeout(500)
        options = _locate_dropdown_options(page, input_loc, field_id)
        count = options.count()
        texts = [options.nth(i).inner_text().strip() for i in range(count)]
    except Exception:
        texts = []
    finally:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    return [t for t in texts if t]


def _locator_for(page, ref_type: str, ref_value: str):
    if ref_type == "id":
        return page.locator(f'[id="{ref_value}"]')
    if ref_type == "data-field-path":
        # Fallback anchor for a field that has NEITHER an id NOR a name
        # attribute of its own -- confirmed on Ashby's Location autocomplete
        # combobox, which renders <input role="combobox"> with no id/name at
        # all. Ashby's own field-wrapper div carries a stable, unique
        # data-field-path attribute instead, so this scopes down to the
        # actual interactive element inside that wrapper.
        return page.locator(
            f'[data-field-path="{ref_value}"] [role="combobox"], '
            f'[data-field-path="{ref_value}"] input, '
            f'[data-field-path="{ref_value}"] select, '
            f'[data-field-path="{ref_value}"] textarea'
        ).first
    return page.locator(f'[name="{ref_value}"]')


def _extract_fields_with_refs(page) -> list:
    """Same detection logic as browser_form_scanner.py, but also returns a
    stable id/name reference for each field so it can be re-located and
    interacted with via Playwright locators afterward, in the same page
    session."""
    return page.evaluate("""
        () => {
            const results = [];
            const labels = Array.from(document.querySelectorAll('label'));
            const seen = new Set();

            // Ashby checkbox-GROUPS: a fieldset with one shared question
            // label plus several individually-labeled option checkboxes.
            // The shared label's `for` attribute points at the fieldset's
            // own id, not at any single <input>, so the generic per-label
            // loop below finds no matching element for it and silently
            // drops the real question -- and each checkbox's own `name`
            // attribute is its OWN option text (e.g. name="Los Angeles
            // (Venice)"), never shared, so the raw_name-based grouping
            // used later never recognizes these as one group either.
            // Handle this shape explicitly with its own field_type
            // ('checkbox-group-option') rather than reusing plain
            // 'checkbox' -- confirmed the hard way that reusing the
            // existing Yes/No checkbox-group machinery here was wrong:
            // that mechanism treats a bank match as "resolved, skip it"
            // without ever actually checking the box, then a DIFFERENT
            // answer-is-literally-yes/no check downstream never checks it
            // either since the real answer here is text like "New York",
            // not "yes". This shape needs its own resolution: match the
            // GROUP question once, then check whichever option's own
            // label the answer text actually matches.
            const groupFieldsets = Array.from(document.querySelectorAll('fieldset.ashby-application-form-input-checkbox-group'));
            for (const fieldset of groupFieldsets) {
                const groupLabel = fieldset.querySelector('label.ashby-application-form-question-title');
                const groupQuestion = groupLabel ? (groupLabel.innerText || '').trim() : '';
                if (!groupQuestion) continue;
                const groupId = groupLabel.getAttribute('for') || groupQuestion;

                const options = Array.from(fieldset.querySelectorAll('.ashby-application-form-input-checkbox-group-option'));
                for (const opt of options) {
                    const input = opt.querySelector('input[type="checkbox"]');
                    const optLabel = opt.querySelector('label');
                    if (!input || !optLabel) continue;

                    const optKey = input.id || input.name;
                    seen.add(optKey);

                    results.push({
                        question: (optLabel.innerText || '').trim(),
                        group_question: groupQuestion,
                        option_label: (optLabel.innerText || '').trim(),
                        field_type: 'checkbox-group-option',
                        required: groupQuestion.includes('*'),
                        ref_type: input.id ? 'id' : 'name',
                        ref_value: input.id || input.name || '',
                        raw_name: 'ashby-group:' + groupId,
                    });
                }
            }

            // Radio-button GROUPS, detected structurally rather than by a
            // guessed Ashby CSS class name (unlike the checkbox handling
            // above, which was confirmed against real markup -- this
            // hasn't been, so flag any failure here for a look at the
            // real DOM the same way). Native radios are REQUIRED by HTML
            // itself to share a `name` attribute for mutual exclusivity
            // to work at all, unlike Ashby's checkboxes which deliberately
            // don't -- so this doesn't need the same raw_name override
            // trick, just the same "find the real shared question" fix.
            // The shared question label is identified by the same broken-
            // reference signature discovered on checkboxes: a <label>
            // whose `for` attribute doesn't match any actual <input> id
            // anywhere on the page (i.e. it's pointing at the group's own
            // wrapper id, not a real field) -- a structural pattern, not
            // tied to one ATS's naming conventions, so this should also
            // work for a checkbox group that ISN'T specifically Ashby's.
            const allInputIds = new Set(Array.from(document.querySelectorAll('input[id]')).map(el => el.id));
            const handledFieldsets = new Set(groupFieldsets);
            for (const fieldset of Array.from(document.querySelectorAll('fieldset'))) {
                if (handledFieldsets.has(fieldset)) continue;

                const orphanLabel = Array.from(fieldset.querySelectorAll('label')).find(l => {
                    const forId = l.getAttribute('for');
                    return forId && !allInputIds.has(forId);
                });
                const groupQuestion = orphanLabel ? (orphanLabel.innerText || '').trim() : '';
                if (!groupQuestion) continue;

                const inputs = Array.from(fieldset.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                if (inputs.length < 2) continue;
                handledFieldsets.add(fieldset);

                const groupId = orphanLabel.getAttribute('for') || groupQuestion;
                const widgetType = inputs[0].type;

                for (const input of inputs) {
                    const optLabel = (input.id && document.querySelector('label[for="' + CSS.escape(input.id) + '"]'))
                        || input.closest('label');
                    if (!optLabel) continue;

                    seen.add(input.id || input.name);

                    results.push({
                        question: (optLabel.innerText || '').trim(),
                        group_question: groupQuestion,
                        option_label: (optLabel.innerText || '').trim(),
                        field_type: widgetType === 'radio' ? 'radio-group-option' : 'checkbox-group-option',
                        required: groupQuestion.includes('*'),
                        ref_type: input.id ? 'id' : 'name',
                        ref_value: input.id || input.name || '',
                        raw_name: 'group:' + groupId,
                    });
                }
            }

            for (const label of labels) {
                const text = label.innerText || '';
                if (!text.trim()) continue;

                let field = null;
                const forId = label.getAttribute('for');
                if (forId) {
                    field = document.getElementById(forId);
                    if (!field) field = document.querySelector('[name="' + CSS.escape(forId) + '"]');
                }
                if (!field) field = label.querySelector('input, select, textarea');
                if (!field && label.parentElement) {
                    // Handles a label/field pair that are SIBLINGS under a
                    // shared wrapper rather than label-wraps-field or a
                    // working `for` reference -- confirmed against real
                    // markup on Ashby's Location autocomplete, whose label
                    // has a `for` pointing at a non-existent id and whose
                    // <input role="combobox"> lives in a sibling div instead
                    // of nested inside the label itself.
                    field = label.parentElement.querySelector('[role="combobox"], input, select, textarea');
                }
                if (!field) continue;

                const key = field.id || field.name || text;
                if (seen.has(key)) continue;
                seen.add(key);

                let fieldType = field.tagName.toLowerCase();
                if (fieldType === 'input') fieldType = field.type || 'text';

                if (field.getAttribute('role') === 'combobox') {
                    const container = field.closest('.select__container') || field.parentElement;
                    const isMulti = container && !!container.querySelector('[class*="is-multi"]');
                    fieldType = isMulti ? 'react-select-multi' : 'react-select';
                }

                let questionText = text;
                if (fieldType === 'file') {
                    const idOrName = ((field.id || field.name || '')).toLowerCase();
                    if (idOrName.includes('resume') || idOrName.includes('cv')) questionText = 'Resume';
                    else if (idOrName.includes('cover')) questionText = 'Cover Letter';
                    else if (idOrName) questionText = text + ' (' + idOrName + ')';
                }

                const required = field.required === true
                    || field.getAttribute('aria-required') === 'true'
                    || text.includes('*')
                    || label.className.toLowerCase().includes('required');

                // Ref computation: prefer id, then name, same as always --
                // but some fields (confirmed: Ashby's Location combobox)
                // have NEITHER. Fall back to the closest ancestor's
                // data-field-path attribute (Ashby's own stable per-field
                // wrapper anchor) so this field can still be re-located and
                // interacted with later via _locator_for's matching
                // "data-field-path" branch, instead of getting an empty,
                // unusable ref_value.
                let refType = field.id ? 'id' : (field.name ? 'name' : null);
                let refValue = field.id || field.name || '';
                if (!refType) {
                    const wrapper = field.closest('[data-field-path]');
                    if (wrapper) {
                        refType = 'data-field-path';
                        refValue = wrapper.getAttribute('data-field-path');
                    } else {
                        refType = 'name';  // preserves prior behavior (empty ref_value) if no anchor exists at all
                    }
                }

                results.push({
                    question: questionText,
                    field_type: fieldType,
                    required: required,
                    ref_type: refType,
                    ref_value: refValue,
                    raw_name: field.name || '',
                });
            }
            return results;
        }
    """)


def _goto_application_page(page, url: str):
    """Navigates to a job's application page. Uses domcontentloaded instead
    of networkidle -- confirmed the hard way that networkidle times out on
    a real chunk of postings (chat widgets, analytics beacons, background
    polling never let network activity fully stop for 500ms), which would
    otherwise fail the whole scan/fill on pages that actually loaded fine.
    domcontentloaded plus the explicit wait below is the standard, more
    reliable pattern for this. Ashby application forms live at .../application,
    not the bare posting URL."""
    target_url = url
    if "ashbyhq.com" in url and not url.rstrip("/").endswith("/application"):
        target_url = url.rstrip("/") + "/application"

    page.goto(target_url, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)  # lets JS-rendered fields (react-select etc.) finish hydrating


def scan_fields_only(url: str) -> list:
    """Opens the real live application page and returns the raw scanned
    fields (question, field_type, and real dropdown options for
    react-select fields) with NO filling, NO answer-bank lookups, NO
    escalation, and NO submission -- just the same navigation +
    extraction fill_application() does before it starts acting on
    anything, plus a peek at each dropdown's real options. Used by
    form_field_audit.py to check what questions a posting actually asks
    (and whether the answer bank would cover them) without spending a
    Telegram message, a Claude call, or generating any materials."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _goto_application_page(page, url)

        fields = _extract_fields_with_refs(page)

        for f in fields:
            if f["field_type"] in ("react-select", "react-select-multi"):
                loc = _locator_for(page, f["ref_type"], f["ref_value"])
                f["options"] = _peek_react_select_options(page, loc, f["ref_value"])
            else:
                f["options"] = []

        browser.close()
        return fields



def has_separate_upload_slots(fields: list) -> bool:
    """True if the form has a distinct Cover Letter upload field (meaning
    Resume and Cover Letter go up as two separate files) -- False if
    there's only a Resume/CV slot, meaning cover letter + resume need to
    be combined into one PDF (see pdf_builder.build_combined_resume_
    coverletter()). Matches the exact labels _extract_fields_with_refs
    assigns to file-type fields above."""
    file_questions = {f["question"] for f in fields if f["field_type"] == "file"}
    return "Cover Letter" in file_questions
