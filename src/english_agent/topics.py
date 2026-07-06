WEEKS: dict[int, list[str]] = {
    1: ["My Job", "My Routine", "My Goals", "My City", "A Problem I Solved"],
    2: ["Technology", "Artificial Intelligence", "Economy", "Books", "Health"],
    3: ["Opinions", "Comparisons", "Arguments", "Essays", "Formal Letters", "Reports"],
    4: ["Personal Diary", "Emails", "Summaries", "Opinions"],
    5: ["Stories", "Technical Explanations", "Reviews", "Debates", "Article Summaries"],
}

CONNECTORS = [
    "Nevertheless", "Moreover", "Consequently", "In contrast", "On the other hand",
    "Although", "Whereas", "Hence", "Therefore", "Despite", "Provided that",
]

# ─── READING TOPICS (5-week curriculum, mirrors writing WEEKS) ─────

READING_WEEKS: dict[int, list[str]] = {
    1: [
        "Science & Technology",
        "Space Exploration",
        "Artificial Intelligence",
        "Climate Change",
        "Renewable Energy",
    ],
    2: [
        "Global Health & Medicine",
        "Nutrition & Diet",
        "Mental Health",
        "Diseases & Prevention",
        "Healthcare Systems",
    ],
    3: [
        "Education Systems",
        "Learning Methods",
        "Student Life",
        "Online Learning",
        "Early Childhood Education",
    ],
    4: [
        "World Economies",
        "Global Trade",
        "Financial Markets",
        "Poverty & Wealth",
        "Sustainable Development",
    ],
    5: [
        "Cultural Traditions",
        "Art & Literature",
        "Historical Events",
        "Social Media",
        "Entertainment Industry",
    ],
}

READING_LEVELS: list[str] = [
    "Cambridge A2 (KET)",
    "Cambridge B1 (PET)",
    "Cambridge B2 (FCE)",
    "Cambridge C1 (CAE)",
    "Cambridge C2 (CPE)",
    "IELTS (4.0-5.0)",
    "IELTS (5.5-6.0)",
    "IELTS (6.5-7.0)",
    "IELTS (7.5-9.0)",
    "TOEFL (40-60)",
    "TOEFL (61-80)",
    "TOEFL (81-100)",
    "TOEFL (101-120)",
    "General",
]

READING_TIME_MINUTES = 20
QUESTIONS_PER_GAME = 6
