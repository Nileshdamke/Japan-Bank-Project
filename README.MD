# 🚀 Python Project Setup Guide
## 1️⃣ Create a Virtual Environment

```bash
python -m venv venv
---
## 2. Activate the Virtual Environment
On Windows (cmd/PowerShell)

```bash
.\venv\Scripts\activate

---

## 3. If You Encounter an Error While Activating
If you see an error related to script execution policy, run the following command to allow scripts for the current process:

```bash

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

```
## 4. Try Activating the Virtual Environment Again
On Windows (cmd/PowerShell)

```bash
.\venv\Scripts\activate

----

## 5 Install Required Packages

```bash
pip install -r requirements.txt
----

## 6 Run the Project

```bash
python main.py
----

## 7 Deactivate Virtual Environment
When you’re done:

```bash
deactivate
---