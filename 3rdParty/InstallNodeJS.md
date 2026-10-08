# Node.js & NPM Portable Setup Guide

This guide explains how to configure Node.js and NPM on Windows using the standalone ZIP archive (without using the official installer).

---

## 📋 Steps for Installation

### 1. Extract the Archive
1. Move your downloaded `.zip` file to a permanent directory (e.g., `C:\NodeJS`).
2. Extract all contents directly into that folder. 
3. *Note: You should see `node.exe`, `npm.cmd`, and `npx.cmd` in the root of this folder.*

### 2. Configure Windows Environment Variables
To run `node` and `npm` commands from any terminal, add the path to your Windows Environment Variables:

1. Press `Win + R`, type **`sysdm.cpl`**, and press **Enter**.
2. Navigate to the **Advanced** tab and click **Environment Variables...**.
3. Under **User variables** (or System variables), select **`Path`** and click **Edit...**.
4. Click **New** and paste the exact path to your folder (e.g., `C:\NodeJS`).
5. Click **OK** on all windows to save.

### 3. Verify Installation
Open a **new** Command Prompt or PowerShell window and run:

```cmd
node -v
npm -v
```

---

## 🛠️ Portable Global Packages Configuration

By default, global npm packages (`npm i -g <package>`) are stored in your user profile. To make your global packages completely portable and hosted within your extracted folder instead, run these steps:

1. Create a new folder named `node_global` inside your Node directory (e.g., `C:\NodeJS\node_global`).
2. Open your terminal and link npm to this folder:
   ```cmd
   npm config set prefix "C:\NodeJS\node_global"
   ```
3. Add this new path (`C:\NodeJS\node_global`) to your Windows **`Path`** environment variable (repeat Step 2 above) so Windows can find your global CLI executables.
