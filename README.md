# Amazon SEO Article Agent (100% Free)

ASIN দিয়ে Amazon প্রোডাক্ট ডেটা স্ক্র্যাপ করে, ফ্রি **Groq AI** (Llama 3.3 70B)
দিয়ে SEO আর্টিকেল লিখে, প্রতিটা আর্টিকেলকে **এডিটেবল Word (.docx) ফাইল**
হিসেবে তৈরি করে দেয়। কোনো WordPress কানেকশন লাগে না, কোনো পেইড API/সার্ভিস নেই।

## এটা কীভাবে কাজ করে
1. তুমি `jobs.csv` ফাইলে ঠিক করে দাও — কোনটা `single` (১টা ASIN), কোনটা `vs` (২-৩টা ASIN)।
2. GitHub Actions-এ ম্যানুয়ালি "Run workflow" চাপো।
3. Agent প্রতিটা ASIN-এর পেজ থেকে টাইটেল, দাম, রেটিং, ছবি, ফিচার স্ক্র্যাপ করে।
4. Groq (ফ্রি, খুবই দ্রুত) দিয়ে SEO-friendly আর্টিকেল লেখে।
5. প্রতিটা আর্টিকেল একটা আলাদা `.docx` (Word) ফাইলে সেভ করে — প্রোডাক্ট ছবিসহ,
   হেডিং/বুলেট/টেবিল ফরম্যাট করা অবস্থায়, সরাসরি এডিট করা যায়।
6. রান শেষে GitHub Actions-এর **Artifacts** সেকশন থেকে সব `.docx` ফাইল
   একসাথে ZIP আকারে ডাউনলোড করা যায়।
7. কাজ শেষ → GitHub runner নিজে থেকেই বন্ধ হয়ে যায়। কোনো background চলতে থাকে না।

## ⚠️ সত্যিটা জেনে রাখো (জরুরি)
- Amazon ওদের পেজ স্ক্র্যাপ করা পছন্দ করে না এবং মাঝে মাঝে bot ব্লক করে/CAPTCHA দেখায়,
  বিশেষ করে cloud IP (GitHub Actions) থেকে রিকোয়েস্ট গেলে। তাই **মাঝে মাঝে কিছু ASIN
  ফেইল হতে পারে** — agent সেগুলো স্কিপ করে বাকিগুলো চালিয়ে যাবে, আর
  `run_summary.json`-এ কোনটা ফেইল হলো তা লেখা থাকবে।
- এটা ব্যক্তিগত/গবেষণা ব্যবহারের জন্য বানানো। Amazon-এর Terms of Service অনুযায়ী
  স্বয়ংক্রিয় স্ক্র্যাপিং নিষিদ্ধ হতে পারে — নিজ দায়িত্বে ব্যবহার করো, এবং রিকোয়েস্টের
  ফ্রিকোয়েন্সি কম রাখাই ভালো (দিনে ৫-১০টা যথেষ্ট কম)।
- Groq free tier-এর একটা daily request limit আছে (বড় মডেলে দিনে প্রায় ১,০০০
  রিকোয়েস্ট, যা ৫-১০ আর্টিকেলের জন্য যথেষ্ট বেশি), ভবিষ্যতে limit বদলাতে পারে।
- GitHub Actions Artifacts ৯০ দিন পর্যন্ত রাখা হয় (default), তারপর নিজে থেকেই
  মুছে যায় — তাই রান শেষে সময়মতো ডাউনলোড করে নিজের কম্পিউটারে রাখাই ভালো।

## Setup (একবারই করতে হবে)

### ১. এই ফোল্ডারটা একটা GitHub repo-তে push করো
Public repo হলে GitHub Actions minutes সম্পূর্ণ ফ্রি ও আনলিমিটেড।
Private repo হলেও মাসে ২০০০ মিনিট ফ্রি — যথেষ্ট বেশি এই কাজের জন্য।

**গুরুত্বপূর্ণ:** এই ফোল্ডারের ভেতরের ফাইলগুলো (README.md, main.py,
scraper.py ইত্যাদি) সরাসরি repo-র **রুটে** থাকতে হবে — কোনো সাব-ফোল্ডারের
ভেতরে না। ZIP আপলোড করলে extract করা ফোল্ডারের *ভেতরে* ঢুকে সব ফাইল
সিলেক্ট করে আপলোড করো, ফোল্ডারটা নিজে না।

### ২. ফ্রি Groq API key নাও
- যাও: https://console.groq.com/keys
- Google/GitHub দিয়ে সাইনআপ করো (ফ্রি, কোনো কার্ড লাগে না)
- "Create API Key" চাপো, নাম দাও (যেমন "article-agent")
- জেনারেট হওয়া key (শুরুতে `gsk_`) কপি করে রাখো — এটা শুধু একবারই দেখাবে

### ৩. GitHub repo-তে Secret যোগ করো
Repo → Settings → Secrets and variables → Actions → "New repository secret"

| Secret name    | Value                                 |
|-----------------|-----------------------------------------|
| GROQ_API_KEY    | ধাপ ২ থেকে পাওয়া key (gsk_ দিয়ে শুরু)  |

শুধু এই **একটা** secret-ই লাগবে — WordPress-এর কোনো ইউজারনেম/পাসওয়ার্ড
এখন আর দরকার নেই।

## প্রতিদিনের ব্যবহার

1. `jobs.csv` ফাইল এডিট করো (GitHub-এর web editor দিয়েই করা যায়, কোনো
   কোডিং লাগে না):

```csv
type,focus_keyword,asins
single,best wireless earbuds under 50,B0CHWRXH8B
vs,budget blender comparison,B08P29T3WW;B0018UI4T6
```

   - `type` = `single` অথবা `vs`
   - `focus_keyword` = যে keyword-এ rank করাতে চাও
   - `asins` = একটা ASIN (single-এর জন্য) অথবা ২-৩টা ASIN সেমিকোলন (`;`) দিয়ে
     আলাদা করে (vs-এর জন্য)
   - সর্বোচ্চ ১০টা জব একবারে চলবে (তোমার দিনে ৫-১০টার প্ল্যান অনুযায়ী)

2. commit করো (save)।

3. GitHub repo → **Actions** ট্যাব → "Generate Amazon Articles" workflow →
   **Run workflow** বাটন চাপো।

4. কয়েক মিনিট পর সেই run-এর পেজে নিচের দিকে **Artifacts** সেকশনে
   "generated-articles" নামে একটা ZIP দেখাবে — ডাউনলোড করো।

5. ZIP extract করলে প্রতিটা আর্টিকেলের জন্য একটা করে `.docx` ফাইল পাবে
   (যেমন `01_Best_Wireless_Earbuds.docx`)। এটা Word, Google Docs, বা
   LibreOffice-এ খুলে এডিট করা যায়, তারপর চাইলে WordPress-এ (বা যেকোনো
   জায়গায়) নিজে হাতে কপি-পেস্ট করে বসাতে পারবে।

6. কাজ শেষ হয়ে গেলে GitHub Actions runner নিজে থেকেই বন্ধ হয়ে যাবে —
   কিছু বন্ধ করার দরকার নেই।

## Manual product-data fallback (new)

Amazon may block GitHub Actions even when the product page opens normally in your own browser. To keep an article job moving without guessing product facts, use `manual_data.csv`.

- Add one row per ASIN you want to provide manually.
- If an ASIN exists in `manual_data.csv`, the agent uses that row and does not request that ASIN from Amazon.
- If there is no manual row, the agent tries the Amazon scraper as before.
- A manual row must include the exact 10-character ASIN and product title. Other fields are optional.
- Separate multiple feature bullets with a pipe character (`|`).
- Enter only facts verified from the actual Amazon listing or another reliable product source. Leave unknown fields blank; the article writer is instructed not to invent missing prices, ratings, counts or specifications.

CSV columns (keep this exact header):

```csv
asin,title,price,rating,review_count,image_url,features,url
```

Example row (illustrative format only — replace with verified product facts):

```csv
B01728NLRG,"Exact product title from listing",$29.99,4.5,1200,https://example.com/image.jpg,"Feature one|Feature two|Feature three",https://www.amazon.com/dp/B01728NLRG
```

You can manually enter only the ASIN and title; price, rating, review count, image and features can stay blank. Without at least a verified title, the agent will not use the row.

**Workflow status is also corrected:** if no article is generated, the GitHub Actions run now exits with an error instead of showing a misleading green success. If at least one article is generated, successful documents are retained and the run completes.

## যদি কোনো ASIN বার বার ফেইল হয়
- সেই ASIN-টার Amazon পেজ ব্রাউজারে খুলে দেখো এটা এখনো available কিনা।
- ২৪ ঘণ্টা পর আবার ট্রাই করো (temporary block হতে পারে)।
- `run_summary.json` (Artifacts-এই পাবে) খুলে দেখো কোন job-এ কী কারণে
  ফেইল হয়েছে।

## ফাইল স্ট্রাকচার
```
amazon-article-agent/
├── .github/workflows/generate-articles.yml  ← GitHub Actions workflow (manual trigger)
├── jobs.csv            ← তুমি এডিট করবে প্রতিদিন
├── scraper.py           ← Amazon থেকে ডেটা আনে (Playwright)
├── llm_generator.py     ← Groq দিয়ে আর্টিকেল লেখে
├── doc_writer.py         ← আর্টিকেলকে .docx ফাইলে কনভার্ট করে
├── main.py               ← সব একসাথে চালায়
└── requirements.txt
```

## লোকাল টেস্ট (অপশনাল)
```bash
pip install -r requirements.txt
playwright install chromium --with-deps
export GROQ_API_KEY=xxx
python main.py
# output/ ফোল্ডারে .docx ফাইলগুলো পাবে
```
