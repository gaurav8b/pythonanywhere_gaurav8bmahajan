# Deployment Guide: Automated Product Catalyst (Free Plan Workaround)

This guide is updated for the PythonAnywhere free plan. It uses a `config.py` file to store the API key instead of environment variables.

## Step 1: Get a Google AI API Key

1.  Go to **Google AI Studio**: [https://aistudio.google.com/](https://aistudio.google.com/)
2.  Log in and click **"Get API key"**.
3.  Click **"Create API key in new project"**.
4.  Copy the generated API key and save it. You will need it in Step 2.

## Step 2: Create Your Local Project Files

On your local machine, ensure your `automated_product_catalyst` directory contains the updated `app.py` and the **new `config.py` file**.

1.  Open the new `config.py` file.
2.  Paste your Google AI API key into it, replacing `"PASTE_YOUR_API_KEY_HERE"`.
3.  Save the file.

## Step 3: Upload and Set Up The Project

1.  **Compress Your Project:** Create a `.zip` file of the `automated_product_catalyst` directory containing the new `config.py` file.
2.  **Upload to PythonAnywhere:** Go to the "Files" tab on PythonAnywhere. If you have an old `automated_product_catalyst` directory, delete it. Then, upload your new ZIP file and unzip it in a Bash console.
3.  **Install Dependencies:** Activate your virtualenv (`workon catalyst-venv`) and install the required libraries:
    ```bash
    pip install -r /home/yourusername/automated_product_catalyst/requirements.txt
    ```

## Step 4: Configure the Web App

1.  Go to the **"Web" tab** for your catalyst application.
2.  **Virtualenv:** Ensure your `catalyst-venv` is configured.
3.  **WSGI Configuration:** Ensure your WSGI file is configured to point to your `app.py`.
4.  **Static Files:** Ensure your static files mapping is correct.

## Step 5: Reload and Launch

1.  Go back to the **"Web" tab**.
2.  Click the big green **"Reload..."** button.
3.  Navigate to your app's URL. The application should now work.

> ### **SECURITY WARNING**
>
> The `config.py` file contains your secret API key. **Do not share this file or upload it to a public place like GitHub.** If you use Git for version control, you should create a `.gitignore` file and add `config.py` to it. This is the most significant drawback of not being able to use environment variables.
