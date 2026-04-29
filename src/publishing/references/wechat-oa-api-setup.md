# WeChat Official Account API Setup

Updated for this workspace on **2026-04-13**.

## Official docs confirmed

- Material upload:
  - official page: <https://developers.weixin.qq.com/doc/offiaccount/Asset_Management/New_temporary_materials.html>
  - endpoint family includes `/cgi-bin/media/upload`
- Draft box:
  - official page: <https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html>
  - endpoint family includes `/cgi-bin/draft/add`
- Publish:
  - official page: <https://developers.weixin.qq.com/doc/offiaccount/Publish/Publish.html>
  - endpoint family includes `/cgi-bin/freepublish/submit`

## Important eligibility note

The current official publish page states:

- starting in **July 2025**,
- personal主体账号,
- enterprise主体未认证账号,
- and accounts that do not support certification

will have the publish-interface permissions reclaimed.

This means API publishing is only realistic if the user’s OA account still has article-publish API access.

## What to assume in this repo

- Generate `wechat.docx` first.
- The default workspace path is manual import through the WeChat Official Account backend, not API draft publishing.
- The current practical flow is:
  1. open the OA backend,
  2. import the generated `wechat.docx`,
  3. review cover, inline images, and references,
  4. publish manually.
- If a future run needs API publishing, that should be treated as a separate implementation track:
  1. get `access_token`,
  2. upload required cover / inline media,
  3. create a draft,
  4. submit the draft for publish,
  5. poll publish status when needed.
