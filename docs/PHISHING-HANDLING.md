# Handling phishing reports safely

A short procedure for investigating a phishing message and reporting it. General patterns only; nothing here comes from a private case. Written 2026-10-22.

## Principles
- **Look, don't touch.** Never click, sign in, type anything, run a file, or solve a CAPTCHA. Inspect with public tools or an isolated session that is not signed in to any real account.
- **Verified vs inferred.** Mark every statement in a report as one or the other. "Verified" means you saw it yourself (a header, a page, a scan result). Everything else is inferred.
- **No personal data.** Reports never contain the victim's name, address, phone, account details, or the full original message body. Describe, don't forward.
- **No warnings in someone else's name.** Don't send alerts to third parties as the victim. Report only to official abuse channels.
- **Free and legal only.** No paid services, no scraping that breaks a site's terms, no attempts to access the attacker's systems.

## Steps
1. **Preserve.** Keep the original message as an attachment (forwarding inline loses headers). Note the date, sender address, subject, and every link and attachment name. Compute file hashes without opening files.
2. **Headers.** Check SPF, DKIM and DMARC results and the real sending path. Say whether the message is signed and by whom.
3. **Links.** Don't open them from a real device. Use public URL scanners or an isolated browser, and record redirects, final host, and what the page asks for. Note if the page shows different content by country or device.
4. **Attachments.** Static checks only: hash, file type, strings, public reputation lookup. Upload to a free public sandbox only if the file is an attack sample and contains no private data.
5. **Infrastructure.** For each domain: registrar, registration date, name servers and CDN. For each host IP: network owner and ASN, and the abuse contact from the regional registry (for example RIPE for Europe and the Middle East). Check public blocklists and feeds for prior reports.
6. **Report.** Send to verified abuse addresses taken from official sources: the hosting provider, the registrar, the CDN, the impersonated brand's phishing address, and the national CERT. Also submit to browser safe-browsing and blocklist feeds that don't need an account or a CAPTCHA. If a form needs a CAPTCHA or a signup, skip it and say so.
7. **Follow up.** Keep case numbers and auto-replies. Re-check later whether the domain, page or certificate was taken down, and note whether it followed your report.
8. **Close.** Tell the person what was found, what was reported, and what was skipped. Then delete the phishing message from their inbox.

## Report template (factual)
```
Subject: Phishing site hosted on <IP/domain> - abuse report

Summary: <one sentence: what it impersonates and what it asks for>
First seen: <date/time UTC>
URL(s): <defanged, e.g. hxxps://example[.]invalid/path>
Host: <IP>, <network owner>, <ASN>
Domain: <domain>, registrar <name>, registered <date>
Verified: <what you saw directly>
Inferred: <what you believe but did not confirm>
Evidence: <scan report links, header excerpts, hashes>
Request: please suspend the site and preserve logs.
No personal data is included.
```

## Practice sample (synthetic)
A made-up message, safe to analyze on paper only:
- From: `billing@invoices-example.invalid`, subject "Your subscription expired".
- Link text "Renew now" points to `hxxps://renew-account[.]example[.]invalid/login`.
- Headers: SPF fail, no DKIM, DMARC none, sender domain registered 2 days ago (fictional).
- The page, if it existed, would ask for card details.
Task: write the report using the template, marking verified and inferred lines. Use only what the sample says; invent nothing.
