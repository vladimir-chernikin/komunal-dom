    const chatMessages = document.getElementById('chatMessages');
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const tokenCounter = document.getElementById('tokenCounter');
    const tokenCountEl = document.getElementById('tokenCount');
    const rublesCostEl = document.getElementById('rublesCost');

    const TOKEN_PRICE = 0.0002;

    function calculateTokens(text) {
        return Math.ceil(text.length / 4);
    }

    function updateTokenCounter() {
        const text = messageInput.value.trim();
        if (text.length > 0) {
            const tokens = calculateTokens(text);
            const rubles = (tokens * TOKEN_PRICE).toFixed(2);

            tokenCountEl.textContent = tokens;
            rublesCostEl.textContent = rubles;
            tokenCounter.style.display = 'block';
        } else {
            tokenCounter.style.display = 'none';
        }
    }

    function addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = text;

        const meta = document.createElement('div');
        meta.className = 'message-meta';
        meta.textContent = type === 'user' ? 'Вы' : 'Нормативный помощник';

        messageDiv.appendChild(bubble);
        messageDiv.appendChild(meta);

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'loading-indicator';
        loadingDiv.id = 'loadingIndicator';
        loadingDiv.textContent = 'Поиск в нормативных документах...';
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeLoadingIndicator() {
        const loading = document.getElementById('loadingIndicator');
        if (loading) {
            loading.remove();
        }
    }

    function addSearchResults(results) {
        if (!results || results.length === 0) {
            addMessage('К сожалению, ничего не найдено. Попробуйте переформулировать вопрос.', 'bot');
            return;
        }

        results.forEach((result, index) => {
            const resultDiv = document.createElement('div');
            resultDiv.className = 'message bot';

            const bubble = document.createElement('div');
            bubble.className = 'message-bubble';
            bubble.style.maxWidth = '85%';

            const searchResult = document.createElement('div');
            searchResult.className = 'search-result';

            const header = document.createElement('div');
            header.className = 'search-result-header';

            const documentTitle = document.createElement('div');
            documentTitle.className = 'search-result-document';
            documentTitle.textContent = result.document;

            const score = document.createElement('div');
            score.className = 'search-result-score';
            const similarity = (result.similarity * 100).toFixed(1);
            score.textContent = `Схожесть: ${similarity}%`;

            header.appendChild(documentTitle);
            header.appendChild(score);

            const content = document.createElement('div');
            content.className = 'search-result-content';
            content.textContent = result.content;

            const meta = document.createElement('div');
            meta.className = 'search-result-meta';

            if (result.metadata.article) {
                const articleSpan = document.createElement('span');
                articleSpan.innerHTML = `<strong>Статья:</strong> ${result.metadata.article}`;
                meta.appendChild(articleSpan);
            }

            if (result.metadata.app) {
                const appSpan = document.createElement('span');
                appSpan.innerHTML = `<strong>Приложение:</strong> ${result.metadata.app}`;
                meta.appendChild(appSpan);
            }

            if (result.metadata.section) {
                const sectionSpan = document.createElement('span');
                sectionSpan.innerHTML = `<strong>Раздел:</strong> ${result.metadata.section}`;
                meta.appendChild(sectionSpan);
            }

            searchResult.appendChild(header);
            searchResult.appendChild(content);
            if (result.metadata.article || result.metadata.app || result.metadata.section) {
                searchResult.appendChild(meta);
            }

            bubble.appendChild(searchResult);

            const metaInfo = document.createElement('div');
            metaInfo.className = 'message-meta';
            metaInfo.textContent = `Результат ${index + 1} из ${results.length}`;

            resultDiv.appendChild(bubble);
            resultDiv.appendChild(metaInfo);

            chatMessages.appendChild(resultDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });
    }

    function addError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        chatMessages.appendChild(errorDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addTokenUsageInfo(tokensUsed) {
        console.log('addTokenUsageInfo вызван, токенов:', tokensUsed);
        const rubles = (tokensUsed * TOKEN_PRICE).toFixed(2);
        console.log('Рубли:', rubles);

        const infoDiv = document.createElement('div');
        infoDiv.className = 'token-usage-info';
        infoDiv.innerHTML = `
            <strong>Израсходовано токенов: ${tokensUsed}</strong><br>
            Стоимость запроса: ${rubles} руб.
        `;

        console.log('Создан элемент:', infoDiv);
        chatMessages.appendChild(infoDiv);
        console.log('Элемент добавлен в chatMessages');
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    messageInput.addEventListener('input', updateTokenCounter);

    chatForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const message = messageInput.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        messageInput.value = '';
        tokenCounter.style.display = 'none';

        sendButton.disabled = true;
        addLoadingIndicator();

        try {
            const response = await fetch('http://komunal-dom.ru:8002/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query: message,
                    k: 3
                })
            });

            if (!response.ok) {
                throw new Error(`Ошибка HTTP: ${response.status}`);
            }

            const data = await response.json();

            removeLoadingIndicator();

            // Показываем информацию о затратах токенов от сервера
            if (data.tokens_used) {
                addTokenUsageInfo(data.tokens_used);
            }

            if (data.results && data.results.length > 0) {
                // Берем только первые 3 результата
                const topResults = data.results.slice(0, 3);
                addSearchResults(topResults);
            } else {
                addMessage('К сожалению, по вашему запросу ничего не найдено. Попробуйте изменить формулировку.', 'bot');
            }

        } catch (error) {
            removeLoadingIndicator();
            addError(`Ошибка при поиске: ${error.message}. Проверьте, что сервер нормативных документов запущен.`);
            console.error('Ошибка:', error);
        }

        sendButton.disabled = false;
        messageInput.focus();
    });

    messageInput.focus();
