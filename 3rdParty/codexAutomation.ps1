# --- CONFIGURATION ---
\$TargetColumn = "Selected for Development"  # Change this to your exact column name
\$BranchPrefix = "feature"                   # Prefix for the generated git branches

Write-Host "🔍 Fetching tickets from Jira column: '\$TargetColumn'..." -ForegroundColor Cyan

# 1. Ask Codex via MCP to list the ticket keys in the targeted column
JqlQuery = "status = 'TargetColumn'"
\$TicketsRaw = codex run "List only the issue keys matching the JQL: \$JqlQuery. Output just the raw keys separated by commas (e.g. PROJ-123, PROJ-124)."

# Clean up the output string to get an array of keys
TicketList = TicketsRaw.Split(',') | ForEach-Object { \(_.Trim() } \vert{} Where-Object {\)_ -ne "" }

if (\$TicketList.Count -eq 0) {
    Write-Host "✅ No tickets found in '\$TargetColumn'. Exiting." -ForegroundColor Green
    Exit
}

Write-Host "Found \$(TicketList.Count) ticket(s) to process: TicketList" -ForegroundColor Yellow

# 2. Loop through each ticket
foreach (Ticket in TicketList) {
    Write-Host "`n🚀 Processing ticket: $Ticket" -ForegroundColor Blue
    
    # Define a clean branch name (e.g., feature/PROJ-123)
    $BranchName = "$BranchPrefix/$Ticket"
    
    # Create and switch to the new Git branch
    Write-Host "📁 Creating branch: $BranchName" -ForegroundColor Gray
    git checkout -b $BranchName
    
    # Run Codex to fetch the ticket description and write the code
    Write-Host "🤖 Codex is implementing the ticket..." -ForegroundColor Gray
    codex run "Read Jira ticket $Ticket details. Implement the requested code changes, add matching tests, and save the files."
    
    # Git lifecycle: Stage, commit, and push changes
    Write-Host "💾 Committing and pushing changes..." -ForegroundColor Gray
    git add .
    git commit -m "feat: automated implementation for $Ticket"
    git push origin $BranchName
    
    # Optional: Tell Codex to move the ticket out of the queue so it isn't processed again next time
    codex run "Transition Jira ticket $Ticket status to 'In Review'."
    
    # Switch back to the main branch before processing the next ticket
    git checkout main
}

Write-Host "`n🎉 All tickets processed successfully!" -ForegroundColor Green
