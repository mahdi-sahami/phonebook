# Contact Book — Application Policies & Feature Guide

## About This Application

**Contact Book** is a personal phonebook web application that lets you store, organise, and manage all your contacts in one place. It features a clean glassmorphism interface, a full REST API, and an AI-powered assistant.

---

## Core Features

### Contact Management
- **Add contacts**: Every contact must have a name and a phone number. Email and address are optional.
- **Edit contacts**: Any field — name, phone, email, address — can be updated at any time.
- **Delete contacts**: Contacts are permanently removed and cannot be recovered after deletion.
- **Search & filter**: Filter by keyword (name or phone), email, address, and sort alphabetically.

### Contact Fields
| Field   | Required | Description                        |
|---------|----------|------------------------------------|
| name    | Yes      | Full name of the contact           |
| phone   | Yes      | Phone number (any format accepted) |
| email   | No       | Email address (must be valid)      |
| address | No       | Street address or location         |

---

## User Accounts & Privacy

- Every user has a **private, isolated contact list**. You can only see your own contacts — no user can access another user's contacts.
- Contacts are tied to your account. If your account is deleted, all contacts are deleted too.
- Authentication uses **JWT tokens** (industry-standard secure tokens).

---

## AI Assistant Policies

### What the AI Assistant Can Do
1. **Create a contact** — "Add a contact named Marco Rossi, phone 0612345678"
2. **Update a contact** — "Change Marco's phone to 0698765432"
3. **Delete a contact** — "Remove the contact named Sara Bianchi"
4. **Search contacts** — "Find all contacts with phone starting with 06" or "Search for Marco"

### Conversation Privacy
- The AI assistant chat is **session-only**. When you log out or close the browser, the entire conversation is automatically erased.
- No chat messages are stored in the database.
- The AI can only see and manage **your own contacts**, never contacts belonging to other users.

### Limitations
- The AI cannot export or import contact lists.
- The AI cannot change your account password or username.
- The AI cannot merge duplicate contacts (it can search, then you decide).
- The AI will always confirm what action it performed after executing a command.

---

## Search & Filtering Guide

You can search contacts by:
- **Keyword (q)**: matches against name or phone number
- **Email filter**: exact partial match on the email field
- **Address filter**: partial match on the address field
- **Sort order**: name A–Z, name Z–A, phone A–Z, phone Z–A

---

## Usage Rules

1. **No spam contacts**: Do not add fictitious or spam entries.
2. **Personal use**: This application is designed for personal phonebook management.
3. **No sensitive data**: Avoid storing passwords or payment information in contact fields.
4. **Respectful use**: Do not attempt to access other users' contacts.

---

## Technical Notes (for context)

- The backend is built with **Django** and **Django REST Framework**.
- The AI agent uses **GPT-4o** as the language model and **ChromaDB** as the vector database.
- Embeddings are generated with **OpenAI text-embedding-3-small**.
- The agent can execute real database operations on your behalf (create, update, delete, search).

---

## FAQ

**Q: I deleted a contact by mistake. Can I recover it?**
A: No. Deletion is permanent. Always confirm before asking the AI to delete.

**Q: Can I have contacts with the same name?**
A: Yes. There is no uniqueness constraint on name. To avoid confusion, use different phone numbers.

**Q: Does the AI remember my previous conversations?**
A: Only within the current browser session. When you close the browser or log out, the chat history is cleared.

**Q: Can the AI create multiple contacts at once?**
A: Yes, you can ask "Add three contacts: Alice 0611111111, Bob 0622222222, Charlie 0633333333" and the AI will create them one by one.

**Q: What if I give the AI an ambiguous instruction like "delete Marco"?**
A: The AI will search for contacts matching "Marco" and ask you to confirm which one to delete if multiple results are found.
