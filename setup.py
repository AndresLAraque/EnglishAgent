from setuptools import setup, find_packages

setup(
    name="english-agent",
    version="2.0.0",
    description="Personal English vocabulary learning assistant",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "notion-client==1.0.1",
        "python-dotenv",
        "requests",
        "python-telegram-bot[job-queue]>=20.0",
    ],
    entry_points={
        "console_scripts": [
            "english-agent = english_agent.__main__:main",
            "english-bot = english_agent.bot:main",
        ],
    },
)
