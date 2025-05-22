# Shopify App

This is a Shopify app designed to integrate with Shopify stores, allowing users to search for products, manage orders, and view order statuses.

## Features

- Connect to Shopify store
- Search for products
- Add products to cart
- Create and manage orders
- View order status

## Prerequisites

- Python 3.x
- Flask
- Shopify API credentials

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/yourusername/shopify-app.git
    cd shopify-app
    ```

2. Install the required packages:

    ```bash
    pip install -r requirements.txt
    ```

3. Set up environment variables:

    Create a `.env` file in the root directory and add your Shopify API credentials:

    ```
    SHOPIFY_API_KEY=your_api_key
    SHOPIFY_API_SECRET=your_api_secret
    SHOPIFY_CLIENT_ID=your_client_id
    SHOPIFY_CLIENT_SECRET=your_client_secret
    ```

## Usage

1. Run the Flask application:

    ```bash
    flask run
    ```

2. Open your browser and navigate to `http://localhost:5000` to access the app.

## Project Structure

- `app.py`: Main application file
- `templates/`: HTML templates for the app
- `shopify_client.py`: Contains functions for interacting with the Shopify API
- `requirements.txt`: List of Python dependencies

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License.