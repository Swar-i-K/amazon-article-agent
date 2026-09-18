# Amazon SEO Article Agent (100% Free)

ASIN দিয়ে Amazon প্রোডাক্ট ডেটা স্ক্র্যাপ করে, ফ্রি Gemini AI দিয়ে SEO আর্টিকেল লিখে,
WordPress-এ **Draft** হিসেবে সেভ করে দেয়। কোনো পেইড API/সার্ভিস নেই।

## এটা কীভাবে কাজ করে
1. তুমি `jobs.csv` ফাইলে ঠিক করে দাও — কোনটা `single` (১টা ASIN), কোনটা `vs` (২-৩টা ASIN)।
2. GitHub Actions-এ ম্যানুয়ালি "Run workflow" চাপো।
3. Agent প্রতিটা ASIN-এর পেজ থেকে টাইটেল, দাম, রেটিং, ছবি, ফিচার স্ক্র্যাপ করে।
4. Gemini (ফ্রি) দিয়ে SEO-friendly আর্টিকেল লেখে।
5. WordPress-এ Draft হিসেবে পোস্ট করে (কখনও Publish করে না)।
6. কাজ শেষ → GitHub runner নিজে থেকেই বন্ধ হয়ে যায়। কোনো background চলতে থাকে না।

## ⚠️ সত্যিটা জেনে রাখো (জরুরি)
- Amazon ওদের পেজ স্ক্র্যাপ করা পছন্দ করে না এবং মাঝে মাঝে bot ব্লক করে/CAPTCHA দেখায়,
  বিশেষ করে cloud IP (GitHub Actions) থেকে রিকোয়েস্ট গেলে। তাই **মাঝে মাঝে কিছু ASIN
  ফেইল হতে পারে** — agent সেগুলো স্কিপ করে বাকিগুলো চালিয়ে যাবে, আর
  `run_summary.json`-এ কোনটা ফেইল হলো তা লেখা থাকবে।
- এটা ব্যক্তিগত/গবেষণা ব্যবহারের জন্য বানানো। Amazon-এর Terms of Service অনুযায়ী
  স্বয়ংক্রিয় স্ক্র্যাপিং নিষিদ্ধ হতে পারে — নিজ দায়িত্বে ব্যবহার করো, এবং রিকোয়েস্টের
  ফ্রিকোয়েন্সি কম রাখাই ভালো (দিনে ৫-১০টা যথেষ্ট কম)।
- Gemini free tier-এর একটা daily/per-minute request limit আছে (এখন যেটা যথেষ্ট
  বেশি ৫-১০ আর্টিকেলের জন্য), ভবিষ্যতে limit বদলাতে পারে — আপডেট থাকলে
  Google AI Studio ড্যাশবোর্ডে দেখা যাবে।

## Setup (একবারই করতে হবে)

### ১. এই ফোল্ডারটা একটা GitHub repo-তে push করো
Public repo হলে GitHub Actions minutes সম্পূর্ণ ফ্রি ও আনলিমিটেড।
Private repo হলেও মাসে ২০০০ মিনিট ফ্রি — যথেষ্ট বেশি এই কাজের জন্য।

### ২. ফ্রি Gemini API key নাও
- যাও: https://aistudio.google.com/app/apikey
- "Create API key" চাপো (ফ্রি, কোনো কার্ড লাগে না)
- Key-টা কপি করো

### ৩. WordPress Application Password বানাও
- WP Admin → Users → তোমার প্রোফাইল → নিচে "Application Passwords"
- একটা নাম দিয়ে (যেমন "article-agent") "Add New Application Password" চাপো
- জেনারেট হওয়া password কপি করে রাখো (এটা শুধু একবারই দেখাবে)

### ৪. GitHub repo-তে Secrets যোগ করো
Repo → Settings → Secrets and variables → Actions → "New repository secret"

| Secret name       | Value                                   |
|--------------------|------------------------------------------|
| GEMINI_API_KEY     | ধাপ ২ থেকে পাওয়া key                    |
| WP_URL             | `https://yoursite.com` (শেষে `/` ছাড়া)  |
| WP_USERNAME        | তোমার WordPress admin username           |
| WP_APP_PASSWORD    | ধাপ ৩ থেকে পাওয়া password                |

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

4. কয়েক মিনিট পর WordPress Admin → Posts-এ গিয়ে দেখো — সব আর্টিকেল
   **Draft** হিসেবে বসে আছে। রিভিউ করে, দরকার হলে এডিট করে, নিজে হাতে Publish করো।

5. কাজ শেষ হয়ে গেলে GitHub Actions runner নিজে থেকেই বন্ধ হয়ে যাবে —
   কিছু বন্ধ করার দরকার নেই।

## যদি কোনো ASIN বার বার ফেইল হয়
- সেই ASIN-টার Amazon পেজ ব্রাউজারে খুলে দেখো এটা এখনো available কিনা।
- ২৪ ঘণ্টা পর আবার ট্রাই করো (temporary block হতে পারে)।
- অথবা `scraper.py`-এর `scrape_asin(asin)` ফাংশন কল করে ম্যানুয়ালি একবার
  local-এ টেস্ট করে দেখতে পারো (`python scraper.py B0XXXXXXXX`)।

## ফাইল স্ট্রাকচার
```
amazon-article-agent/
├── .github/workflows/generate-articles.yml  ← GitHub Actions workflow (manual trigger)
├── jobs.csv            ← তুমি এডিট করবে প্রতিদিন
├── scraper.py           ← Amazon থেকে ডেটা আনে (Playwright)
├── llm_generator.py     ← Gemini দিয়ে আর্টিকেল লেখে
├── wp_publisher.py       ← WordPress-এ Draft পোস্ট করে
├── main.py               ← সব একসাথে চালায়
└── requirements.txt
```

## লোকাল টেস্ট (অপশনাল)
```bash
pip install -r requirements.txt
playwright install chromium --with-deps
export GEMINI_API_KEY=xxx
export WP_URL=https://yoursite.com
export WP_USERNAME=xxx
export WP_APP_PASSWORD=xxx
python main.py
```
