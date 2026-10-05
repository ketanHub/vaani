from app.domain.tenant import FAQ, TenantProfile

DEMO_CLINIC = TenantProfile(
    id="demo-clinic",
    business_name="Vaani Demo Clinic",
    faqs=[
        FAQ(
            id="hours",
            question="What are your opening hours?",
            answers={
                "en": "We are open Monday to Saturday, 9:00 AM to 7:00 PM.",
                "hi": "हम सोमवार से शनिवार सुबह 9 बजे से शाम 7 बजे तक खुले हैं।",
                "hinglish": "Hum Monday se Saturday 9 AM se 7 PM tak open hain.",
            },
            aliases=[
                "opening time",
                "clinic timing",
                "when are you open",
                "क्लिनिक कब खुलता है",
                "timing kya hai",
            ],
        ),
        FAQ(
            id="location",
            question="Where are you located?",
            answers={
                "en": "This demo clinic is configured for Connaught Place, New Delhi.",
                "hi": "यह डेमो क्लिनिक कनॉट प्लेस, नई दिल्ली के लिए कॉन्फ़िगर किया गया है।",
                "hinglish": "Demo clinic Connaught Place, New Delhi ke liye configured hai.",
            },
            aliases=[
                "address",
                "location",
                "where is the clinic",
                "पता क्या है",
                "clinic kaha hai",
            ],
        ),
        FAQ(
            id="services",
            question="What services do you offer?",
            answers={
                "en": "The demo profile lists general consultations, preventive check-ups, and follow-up consultations.",
                "hi": "डेमो प्रोफ़ाइल में सामान्य परामर्श, प्रिवेंटिव चेक-अप और फॉलो-अप परामर्श शामिल हैं।",
                "hinglish": "Demo profile mein general consultation, preventive check-up aur follow-up consultation listed hain.",
            },
            aliases=[
                "services",
                "treatment",
                "what do you do",
                "क्या सेवाएं हैं",
                "kya services hai",
            ],
        ),
        FAQ(
            id="fee",
            question="What is the consultation fee?",
            answers={
                "en": "The configured demo consultation fee is ₹500.",
                "hi": "कॉन्फ़िगर की गई डेमो परामर्श फीस ₹500 है।",
                "hinglish": "Configured demo consultation fee ₹500 hai.",
            },
            aliases=[
                "price",
                "consultation charges",
                "doctor fee",
                "फीस कितनी है",
                "fees kitni hai",
            ],
        ),
        FAQ(
            id="appointments",
            question="Can I book an appointment?",
            answers={
                "en": "Yes. Appointment intent is captured now; live calendar booking will be enabled when the calendar adapter is configured.",
                "hi": "हाँ। अभी अपॉइंटमेंट अनुरोध कैप्चर किया जाता है; कैलेंडर अडैप्टर कॉन्फ़िगर होने पर लाइव बुकिंग चालू होगी।",
                "hinglish": "Haan. Abhi appointment request capture hoti hai; calendar adapter configure hone ke baad live booking enable hogi.",
            },
            aliases=[
                "book appointment",
                "schedule visit",
                "appointment chahiye",
                "अपॉइंटमेंट बुक करना है",
            ],
        ),
    ],
)
