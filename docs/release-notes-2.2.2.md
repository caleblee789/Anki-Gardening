# Anki Garden 2.2.2

This patch limits the dashboard's application-wide event filter to the keyboard and mouse presses it handles, and attaches dialog content observers after Qt finishes showing the dialog. These changes target crashes seen in hosted layout verification. Welcome reward labels also grow to fit wrapped text at larger font sizes.

It includes the reviewer responsiveness and Growth display improvements from [2.2.1](release-notes-2.2.1.md). Saved Growth, rewards, and balances are unchanged. The declared compatibility range is desktop Anki 26.09.2 and newer; exact-package native Anki verification remains pending.
