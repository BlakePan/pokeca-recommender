document.getElementById('cardNameInput').addEventListener('input', function() {
    const input = this.value;
    if (input.length > 2) {
        fetch(`/api/suggestions?query=${encodeURIComponent(input)}`)
            .then(response => response.json())
            .then(data => {
                const list = document.getElementById('suggestionsList');
                list.innerHTML = '';
                data.forEach(item => {
                    const li = document.createElement('li');
                    li.textContent = item;
                    list.appendChild(li);
                });
            });
    }
});
