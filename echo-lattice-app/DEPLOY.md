نشر Carim Store (Flask) على استضافة عامة — دليل سريع

هذا الملف يشرح خطوات نشر تطبيق "Carim Store" إلى خدمة استضافة سحابية مثل Render أو خدمات تدعم Docker. الهدف: جعل الموقع متاحًا للعالم مع HTTPS ويعمل بشكل ثابت.

المتطلبات الأساسية
- حساب على GitHub
- حساب على Render (https://render.com) أو أي مزود يدعم Docker
- ملء المتغيرات السرية في الإعدادات (SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, FACEBOOK_CLIENT_ID, FACEBOOK_CLIENT_SECRET)

ملفّات أُضيفت في المشروع
- Dockerfile  -> لإنشاء صورة Docker وتشغيلها باستخدام gunicorn
- Procfile    -> لتشغيل التطبيق عبر Heroku/Render (بدون Docker)

خطوات النشر عبر Render (الاكثر بساطة)
1. ارفع المشروع على GitHub
   git init
   git add .
   git commit -m "Initial commit for deployment"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git
   git push -u origin main

2. في لوحة Render
   - اختر "New +" -> "Web Service" -> Connect a repository (اختر المستودع الذي رفعت إليه)
   - اختر "Docker" (Render سيستخدم Dockerfile الموجود) أو "Web Service (Python)" واستخدم الأمر بدء gunicorn.
   - اضبط اسم الخدمة، وفرّض الفرع main
   - أضف متغيرات البيئة (ENV):
       SECRET_KEY (قيمة عشوائية طويلة)
       SESSION_COOKIE_SECURE=1
       USE_HTTPS=1
       GOOGLE_CLIENT_ID
       GOOGLE_CLIENT_SECRET
       FACEBOOK_CLIENT_ID
       FACEBOOK_CLIENT_SECRET
       ALLOW_REGISTRATION=1
       RATE_LIMIT_MAX=5
   - اضغط Create. Render سيبني الصورة ويشغّل الخدمة.

3. إعدادات OAuth (Google / Facebook)
   - في إعدادات كل مزود (Google Console, Facebook Developers) أضف Redirect URI الذي يقدمه Render بعد نشر الخدمة.
     مثال: https://your-service-name.onrender.com/api/auth/google/callback
   - ضع القيم (Client ID, Client Secret) في إعدادات البيئة على Render.

نصائح وأمور مهمة
- تأكد من إضافة قيود Redirect URI حرفيًا كما قمت بتسجيلها في مقدم الخدمة.
- إذا أردت فصل الواجهة الأمامية (static SPA) إلى Vercel/Netlify: انشر محتوى المجلد digital-products-store/digital-products-store كـ static site، ثم حدّث API_BASE في الواجهة لتشير إلى endpoint الخاص بالخادم على Render.
- راجع سجلات Render عند حدوث أخطاء (Build logs / Service logs)

إذا أردت، أستطيع:
- إنشاء مستودع GitHub من جهازك ودفع الكود إليه تلقائيًا.
- إعداد خدمة Render تلقائيًا إذا منحتني تفاصيل المستودع أو صلاحيات OAuth (أرشدك خطوة بخطوة ولم أطلب منك مشاركة كلمات مرور).

أخبرني أي خيار تريده: "أعد رفع الكود إلى GitHub" أو "أرشدني خطوة بخطوة لإنشاء خدمة Render" أو "أنشئ PR".
