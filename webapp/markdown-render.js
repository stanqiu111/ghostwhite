import { marked } from "marked"; // Import the markdown converter

// Handle rendering
window.addEventListener('load', () => {
    const contentDivs = document.getElementsByClassName('content');
    for (const contentDiv of contentDivs) {
        const markdownText = contentDiv.innerHTML;
        const htmlOutput = marked(markdownText);
        contentDiv.innerHTML = htmlOutput;
    }
});