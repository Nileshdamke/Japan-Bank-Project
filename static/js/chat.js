// This function will run once the entire HTML page is loaded and ready.
document.addEventListener('DOMContentLoaded', function() {
    try {
        console.log("DEBUG: Chat script is starting.");

        // Find all the necessary HTML elements for the chat widget.
        const chatBubble = document.getElementById('chat-bubble');
        const chatWindowEl = document.getElementById('chat-window');
        const closeChat = document.getElementById('close-chat');
        const chatInput = document.getElementById('chat-input');
        const chatSend = document.getElementById('chat-send');
        const chatMessages = document.getElementById('chat-messages');

        // If any element is missing, log an error and stop the script.
        if (!chatBubble || !chatWindowEl || !closeChat || !chatInput || !chatSend || !chatMessages) {
            console.error("DEBUG: One or more chat UI elements could not be found in the HTML.");
            return;
        }
        console.log("DEBUG: All chat UI elements were found successfully.");

        // Initialize the Bootstrap collapse component for the chat window.
        const chatWindow = new bootstrap.Collapse(chatWindowEl, { toggle: false });
        console.log("DEBUG: Bootstrap collapse component initialized.");

        // --- Event Listeners ---

        // When the chat bubble is clicked, open or close the chat window.
        chatBubble.addEventListener('click', function() {
            console.log("DEBUG: Chat bubble was clicked.");
            chatWindow.toggle();
        });

        // When the 'X' button is clicked, hide the chat window.
        closeChat.addEventListener('click', function() {
            console.log("DEBUG: Close button was clicked.");
            chatWindow.hide();
        });

        // This function handles the logic for sending a message.
        const sendMessage = async function() {
            console.log("DEBUG: Send message function was called.");
            const message = chatInput.value.trim();
            if (message === '') return;

            // Add the user's message to the chat window.
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'chat-message user-message';
            userMessageDiv.textContent = message;
            chatMessages.appendChild(userMessageDiv);
            chatInput.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;

            // Send the message to the server and wait for the AI's response.
            try {
                const response = await fetch("/chat", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message }),
                });
                const data = await response.json();
                
                // Add the bot's response to the chat window.
                const botMessageDiv = document.createElement('div');
                botMessageDiv.className = 'chat-message bot-message';
                botMessageDiv.textContent = data.response || data.error;
                chatMessages.appendChild(botMessageDiv);
            } catch (error) {
                console.error("DEBUG: There was an error sending the message:", error);
            } finally {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        };

        // Attach the sendMessage function to the send button's click event.
        chatSend.addEventListener('click', sendMessage);

        // Also allow sending a message by pressing the Enter key in the input field.
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });

        console.log("DEBUG: All event listeners have been attached successfully.");

    } catch (e) {
        // If any unexpected error occurs during setup, log it to the console.
        console.error("DEBUG: A critical error occurred in the chat script:", e);
    }
});
