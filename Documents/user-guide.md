# User Guide

Advance Search finds documents by meaning. Describe what you need in your own words, and it shows the three
documents most likely to be the one you want, with the passage that matched and a match score.

## How the system works

1. An Admin uploads PDF, Word or Excel files.
2. The text of each file is extracted and split into passages of a few paragraphs (or a group of spreadsheet rows).
3. Each passage is turned into a vector, a list of numbers that captures its meaning, and stored in a search index.
4. When you search, the app looks for passages that share your words **and** passages close in meaning, re-ranks
   the best ones with a semantic ranker, and shows the best documents.

So "how many days off do I get" finds a leave policy that only talks about "annual entitlement".

## Signing in and roles

Open the web app address, choose a role and enter the demo password your administrator gave you.

| Role | Can |
|---|---|
| **Admin** | Search, open documents, upload, re-index and delete documents, sync from storage, rebuild the index, change settings |
| **User** | Search and open documents |

The demo uses one shared password with a role choice. This is for demonstrations only: anyone with the password can
choose Admin. Sign-in with Microsoft Entra ID and real roles is planned. After five wrong passwords from the same
address, sign-in is blocked for 15 minutes. Sessions last 8 hours; use **Sign out** on shared computers.

## Search

- Type in the search bar and press **Enter**. Press **/** anywhere on the page to jump to the search bar, and
  **Esc** to clear it.
- Select an example under the bar to try it. Your last six searches appear under **Recent** (stored only in your
  browser; **Clear** removes them).
- Each result card shows:
  - the rank, file name, type, size and upload date;
  - where the best passage is: *Page 3*, *Section: Lost or stolen devices*, or *Sheet 'Approval limits', rows 2-7*;
  - the passage with your words and related words highlighted;
  - the **match %** and a meter (green is a strong match, amber medium, red weak). Point at it, or tab to it, to see
    where the score came from;
  - **Open document** (opens the original; PDFs open in the browser, Word and Excel files download) and
    **Copy link** (a link to the document; the person opening it must be signed in).
- The line above the results says how many documents were found, how long it took, and how many weaker matches
  were hidden.

### How the match % is calculated

Each document is scored by its best passage:

- **Semantic ranker** (normal case). The semantic ranker of Azure AI Search scores the passage from 0 to 4. The
  match % is that score divided by 4, as a percentage: a score of 3.2 shows **80%**.
- **Vector similarity** (when the ranker is not available, for example after the free monthly quota of 1,000
  semantic queries is used up). The match % is the similarity between the meaning of your query and the passage
  (cosine similarity, 0 to 1) as a percentage.

A document is suggested only if it contains at least one word of your search (or a closely related word), or if
the ranker rates its meaning as genuinely relevant. Documents that share nothing with your search are never shown,
whatever their percentage. Of the rest, only documents that really match are shown: documents under the minimum (30% by default), or under 60% of the
best result's match, are hidden, so a search often shows just one document. A passage with your exact phrase
scores higher, and a code, file name, figure number or "quoted phrase" in your query only finds documents that
contain it. Matching **images** (diagrams, photos, figures) are shown as thumbnails in the result, with their
caption, page or location; select one to open it full size. The match % is a **relevance indicator, not a
probability**: 80% does not mean "80% likely to be right". Use it to compare results with each other.

### When nothing is found

- **No matching documents found**: no document contains your words or matches their meaning well enough. Describe the topic in other words, use fewer and more
  specific words, or check that the document has been uploaded and shows *Indexed*.
- **No documents indexed yet**: nothing has been uploaded, or indexing is still running. Admins see an **Upload
  documents** button.
- **Search is temporarily unavailable**: a service could not be reached. Try again in a moment; Admins see the error.

## Documents (Admin)

- **Upload**: drag files onto the dashed area, or select **browse**. Several files upload one after another with a
  progress bar each.
  - Accepted: PDF (`.pdf`), Word (`.docx`), Excel (`.xlsx`), up to 20 MB each. Older `.doc` and `.xls` files must be
    saved in the new format first.
  - **Text-based PDFs only.** A scanned PDF (an image of a page) has no text to search and shows *No text*. Export
    the document as a PDF from the original program instead of scanning it.
  - A file with exactly the same content as an existing document is refused ("already indexed as …"). A file with
    the same name replaces the earlier version.
  - Spreadsheets work best with one header row at the top of each sheet. Hidden sheets are ignored.
- **Status** updates by itself every few seconds while anything is in progress:

| Status | Meaning |
|---|---|
| Queued | Waiting for the indexer (one file at a time) |
| Processing | Text is being extracted, split and indexed |
| Indexed | Searchable; *Passages* shows how many passages it has |
| No text | No text could be extracted (probably a scan) |
| Failed | Indexing failed; the reason is shown under the name. Fix the file or select Re-index |

- **Row actions**: open, **Re-index** (index the file again), **Delete** (asks for confirmation, then removes the
  file and all its passages).
- **Filter** by name, status or type.
- **Sync from storage**: queues every file in storage that is not indexed (files copied in directly, or failed ones).
- **Rebuild index**: removes everything from the search index and indexes every document again. Needed after the
  embedding model changes; search results are incomplete until it finishes.

## Settings (Admin)

| Setting | Default | Effect |
|---|---|---|
| Number of results | 3 | Documents shown per search (1–10) |
| Minimum match % | 30 | Documents below it are hidden |
| Example queries | 5 | Suggestions under the search bar, one per line |
| Welcome text | – | Shown under the title on the search page |

Changes apply to the next search. **Reset to defaults** returns to the values in `Config/search.yaml`. The
**System** box shows the environment, the services in use and the embedding model.

## Suggested demo walkthrough (10 minutes)

The sample documents describe a fictional company, Meridian Infra Ltd: HR policies, IT security, finance,
procurement, onboarding, product datasheets and a project plan.

1. **Sign in as Admin** (1 min). Point out the role choice and the demo password.
2. **Documents** (2 min). Show the 13 documents, the status chips and the *No text* scan. Drag in a file (for
   example `Supplier-Price-List-2026.xlsx` if you deleted it first) and watch it go from *Queued* to *Indexed*.
3. **Search by meaning** (4 min):
   - `how many days off do I get` → *Leave-Policy-2026.pdf*, although it never says "days off".
   - `my notebook computer went missing on the train` → *Information-Security-Policy.docx*, section *Lost or stolen devices*.
   - `who approves a purchase over five lakh` → *Procurement-Approval-Matrix.xlsx*, sheet *Approval limits*: a spreadsheet row, with the column headers.
   - `how long does the device last on one charge` → *FT-200-Field-Tablet-Specification.pdf*.
   - `when can old security camera recordings be thrown away` → *Records-Retention-Schedule.pdf* (CCTV, 30 days).
   - `football world cup results` → *No matching documents found*.
   - `architecture diagram`, `sm3-wiring-diagram.png` or `figure 1` → the document with the diagram and its thumbnail.

   These results were checked in local mode. With Azure OpenAI and the semantic ranker the match percentages
   differ and the order of the lower results can change.
4. **Explain the match %** (1 min): open *How is the match % calculated?*.
5. **Open and share** (1 min): *Open document*, *Copy link*.
6. **Settings** (1 min): set *Number of results* to 5, search again, then reset.

## Questions people often ask

- **Is my query sent anywhere?** It is turned into a vector by the organisation's own Azure OpenAI resource and
  searched in its own Azure AI Search service. Nothing leaves the organisation's Azure subscription.
- **Can it answer questions?** Not yet: it finds the right documents and passages. Generated answers are on the
  roadmap.
- **Which languages?** English.
- **Why is a scanned PDF not found?** It has no text layer. OCR is on the roadmap.
- **Can Users see every document?** Yes. There is no per-department access yet (planned with Entra ID).

## Troubleshooting

| Problem | What to do |
|---|---|
| "Wrong password" | Check the password with your administrator. After 5 attempts wait 15 minutes |
| "Sign-in is not configured" | The administrator has not set the demo password yet |
| A new document is not found | Wait until it shows *Indexed*; check it is not *No text* or *Failed* |
| An upload is refused | Check the type (`.pdf`, `.docx`, `.xlsx`), the size (20 MB) and that the file opens on your computer |
| The first page load is slow | After a restart the app needs up to a minute to start |
| A warning about vector dimensions | The embedding model changed: an Admin selects **Rebuild index** |
