from flask import Flask, request, jsonify, render_template
import db

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/suggestions', methods=['GET'])
def suggestions():
    query = request.args.get('query', '')
    if query:
        results = db.query_autocomplete(query)
        return jsonify(results)
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)
