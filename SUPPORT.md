# Support

## Raising a support ticket

1. Sign in to the DBCH portal at https://dobigcloudhub.ttns.in with the user ID and password TTNS sent you.
2. Open **Support** in the left menu, then **View Ticket**.
3. Select **+** to raise a new ticket and complete all mandatory fields.
4. Select **Submit** and keep the generated **Ticket ID** for reference.

## Before you raise a ticket

- **Indexing issues:** open the **Documents** page. Failed documents show the error under their name and can be
  re-indexed there. Scanned PDFs show *No text* by design. Logs are in Application Insights (`<prefix>-<env>-*-appi`).
- **Search issues:** check the **Settings** page (number of results, minimum match %) and the *System* box. A warning
  about vector dimensions means the index needs **Rebuild index**.
- **Sign-in issues:** check that the demo password has been set (`deploy.sh --param demoPassword='...'`); after five
  wrong attempts sign-in is blocked for 15 minutes.
- **Deployment issues:** see the troubleshooting section in
  [Documents/deployment-guide.md](Documents/deployment-guide.md#troubleshooting).

Include the environment, the document name, the approximate time (with time zone) and any error text in the ticket.
