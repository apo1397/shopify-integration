import os
import secrets
import requests
from flask import Flask, request, redirect, session, render_template, url_for
from dotenv import load_dotenv
from urllib.parse import urlencode
import logging 
import shopify_client # Added

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Added

app = Flask(__name__)
app.secret_key = secrets.token_hex(16) # Used for session management

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET")
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-04") # Default to a recent stable version
# Define the scopes your app needs

SHOPIFY_SCOPES = "read_customers,write_customers,read_orders,write_orders,write_discounts,read_discounts,read_products,write_draft_orders,read_draft_orders" # Updated scopes

# In-memory store for access tokens (for simplicity, replace with a database in production)
# Structure: { 'shop_domain.myshopify.com': 'access_token_value' }
active_shops = {}

# GraphQL query for customer search
CUSTOMER_SEARCH_QUERY = """
query searchCustomers($query: String!) {
  customers(first: 10, query: $query) {
    edges {
      node {
        id
        firstName
        lastName
        email: defaultEmailAddress {
          emailAddress
        }
        phone: defaultPhoneNumber {
          phoneNumber
        }
        addresses(first: 5) {
          address1
          address2
          city
          zip
          provinceCode
          countryCodeV2
          formatted
          phone
        }
      }
    }
  }
}
"""

@app.route('/')
def index():
    logger.info("Accessing index route. Always redirecting to connect_store to simulate fresh flow.")
    # To ensure a fresh flow, we always redirect to the connect_store page from the root.
    # Session variables like 'shop_url' and 'access_token' will be set during the OAuth process,
    # but this direct redirect bypasses checking them at the entry point.
    return redirect(url_for('connect_store'))

@app.route('/connect')
def connect_store():
    logger.info("Accessing connect_store route. Rendering connect.html.") # Added
    return render_template('connect.html')

@app.route('/install', methods=['POST'])
def install():
    logger.info("Accessing install route (POST).") # Added
    shop = request.form.get('shop')
    if not shop:
        logger.error("Shop parameter missing in install request.") # Added
        return "Error: Missing shop parameter.", 400
    
    logger.info(f"Install request for shop: {shop}") # Added
    # Ensure shop has .myshopify.com, if not, append it
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
        logger.info(f"Appended .myshopify.com. Shop is now: {shop}") # Added

    # Generate a unique state token for CSRF protection
    state = secrets.token_hex(16)
    session['oauth_state'] = state
    logger.info(f"Generated OAuth state: {state} for shop: {shop}") # Added
    
    # Construct the Shopify authorization URL
    redirect_uri = url_for('oauth_callback', _external=True)
    logger.info(f"Redirect URI for OAuth: {redirect_uri}") # Added
    auth_url_params = {
        'client_id': SHOPIFY_CLIENT_ID,
        'scope': SHOPIFY_SCOPES,
        'redirect_uri': redirect_uri,
        'state': state,
        # 'grant_options[]': 'per-user' # Optional: for online access mode
    }
    auth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(auth_url_params)}"
    logger.info(f"Redirecting to Shopify auth URL: {auth_url}") # Added
    
    return redirect(auth_url)

@app.route('/oauth/callback')
def oauth_callback():
    logger.info(f"Accessing oauth_callback route with args: {request.args}") # Added
    # Validate state parameter for CSRF protection
    if request.args.get('state') != session.pop('oauth_state', None):
        logger.warning(f"Invalid OAuth state. Expected: {session.get('oauth_state')}, Got: {request.args.get('state')}") # Added
        return "Error: Invalid state parameter.", 403

    shop_url = request.args.get('shop')
    code = request.args.get('code')

    if not shop_url or not code:
        logger.error(f"Missing shop_url or code in OAuth callback. Shop: {shop_url}, Code: {code}") # Added
        return "Error: Missing shop or code parameter.", 400

    logger.info(f"OAuth callback for shop: {shop_url} with authorization code.") # Added
    # Exchange authorization code for an access token
    token_url = f"https://{shop_url}/admin/oauth/access_token"
    payload = {
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
        "code": code,
    }
    
    logger.info(f"Requesting access token from: {token_url}") # Added
    try:
        response = requests.post(token_url, json=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        token_data = response.json()
        access_token = token_data.get('access_token')

        if access_token:
            active_shops[shop_url] = access_token
            session['shop_url'] = shop_url
            session['access_token'] = access_token # Store in session for current user
            logger.info(f"Successfully obtained access token for {shop_url}. Token: {access_token}") # Masked token
            # In a real app, you'd store this token securely, likely in a database,
            # associated with the shop_url.
            return redirect(url_for('product_search_page')) # Changed redirect to product_search_page
        else:
            logger.error(f"Could not retrieve access token for {shop_url}. Response data: {token_data}") # Added
            return "Error: Could not retrieve access token.", 500
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during token exchange for {shop_url}: {e}", exc_info=True) # Added exc_info for traceback
        return f"Error during token exchange: {e}", 500


def search_customers_by_name(shop_url: str, access_token: str, search_query: str) -> list:
    """Searches for customers by name using the Shopify Admin API."""
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    # The search_query itself will be used, enclosed in double quotes
    # Example: if search_query is "Apoorv", the variable 'query' will be "\"Apoorv\""
    # This assumes your CUSTOMER_SEARCH_QUERY expects a simple string for the 'query' variable.
    payload = {
        'query': CUSTOMER_SEARCH_QUERY,
        'variables': {'query': f'"{search_query}"'} # Use search_query directly, enclosed in quotes
    }
    
    # Debugging: Log types of payload components
    logger.debug(f"Type of CUSTOMER_SEARCH_QUERY: {type(CUSTOMER_SEARCH_QUERY)}")
    # logger.debug(f"Type of query_filter: {type(query_filter)}") # query_filter removed
    logger.debug(f"Type of payload['variables']: {type(payload['variables'])}")
    logger.debug(f"Type of payload['variables']['query']: {type(payload['variables']['query'])}")
    logger.debug(f"Payload before sending: {payload}")

    api_url = f"https://{shop_url}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    logger.info(f"Searching for customers with query: {search_query} on {shop_url}")
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        logger.info(f"response from customer search: {response.json()}")
        response.raise_for_status()
        data = response.json().get('data', {})
        customers_data = data.get('customers', {}).get('edges', [])
        logger.info(f"Customer search response received. Number of edges: {len(customers_data)}")
        return customers_data
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error searching customers: {http_err} - Response: {response.text}", exc_info=True)
        return []
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error searching customers: {req_err}", exc_info=True)
        return []
    except ValueError as json_err: # Includes JSONDecodeError
        logger.error(f"JSON decoding error searching customers: {json_err}", exc_info=True)
        return []
    except Exception as e:
        # This will catch the TypeError if it's still happening before the request is made
        logger.error(f"An unexpected error occurred during customer search preparation or execution: {e}", exc_info=True)
        return []

@app.route('/customer-search', methods=['GET', 'POST'])
def customer_search_page():
    logger.info(f"Accessing customer_search_page. Method: {request.method}")
    shop_url = session.get('shop_url')
    access_token = session.get('access_token')

    if not shop_url or not access_token:
        logger.warning("User not authenticated or session expired. Redirecting to connect.")
        return redirect(url_for('connect_store'))

    customers = []
    customer_search_term = ""

    if request.method == 'POST':
        customer_search_term = request.form.get('customer_search_query', '').strip()
        logger.info(f"Customer search initiated for term: '{customer_search_term}' on shop: {shop_url}")
        if customer_search_term:
            customers_data = search_customers_by_name(shop_url, access_token, customer_search_term)
            # Simplify customer data for template
            for edge in customers_data:
                node = edge.get('node', {})
                # Extract email and phone safely
                email_node = node.get('email')
                email_address = email_node.get('emailAddress') if email_node else 'N/A'
                
                phone_node = node.get('phone')
                phone_number = phone_node.get('phoneNumber') if phone_node else 'N/A'

                customers.append({
                    'id': node.get('id'),
                    'firstName': node.get('firstName'),
                    'lastName': node.get('lastName'),
                    'email': email_address,
                    'phone': phone_number,
                    'addresses': node.get('addresses', [])
                })
        else:
            logger.info("Empty customer search term provided.")

    return render_template('products.html', 
                           shop_url=shop_url, 
                           customers=customers, 
                           customer_search_term=customer_search_term,
                           # Make sure to pass other variables needed by products.html
                           products=session.get('current_products', []), 
                           search_term=session.get('last_product_search', ''),
                           cart_items=session.get('cart_items_display', []),
                           total_cart_value=session.get('total_cart_value_display', 0.0),
                           countries=session.get('countries_for_template', []))


@app.route('/products', methods=['GET', 'POST'])
def product_search_page():
    logger.info(f"Accessing product_search_page. Method: {request.method}")
    shop_url = session.get('shop_url')
    access_token = session.get('access_token')

    if not shop_url or not access_token:
        logger.warning("User not authenticated or session expired. Redirecting to connect.")
        return redirect(url_for('connect_store'))

    products = []
    search_term = ""
    cart = session.get('cart', {}) # Initialize or get cart from session

    # Define a list of countries. In a real app, this could be more comprehensive
    # or loaded from a configuration file.
    # Using a subset based on the error message and common countries.
    countries = [
        ("US", "United States"),
        ("CA", "Canada"),
        ("GB", "United Kingdom"),
        ("IN", "India"),
        ("AU", "Australia"),
        ("DE", "Germany"),
        ("FR", "France"),
        ("JP", "Japan"),
        ("CN", "China"),
        ("BR", "Brazil"),
        # Add more countries as needed from the list provided in the error message
        # For example:
        ("AF", "Afghanistan"), ("AL", "Albania"), ("DZ", "Algeria"), 
        ("AE", "United Arab Emirates"), ("ZW", "Zimbabwe")
    ]

    if request.method == 'POST':
        if 'search_query' in request.form:
            search_term = request.form.get('search_query', '').strip()
            logger.info(f"Product search initiated for term: '{search_term}' on shop: {shop_url}")
            if search_term:
                products_data = shopify_client.search_products(shop_url, access_token, search_term)
                # Simplify product data for template
                logger.info(f"Products data received: {products_data}") 
                if products_data: # Add this check
                    for edge in products_data.get('products'):
                        if edge: # Add this check to ensure edge is not None
                            node = edge.get('node', {})
                            variants = []
                            if node.get('variants') and node['variants'].get('edges'):
                                for var_edge in node['variants']['edges']:
                                    var_node = var_edge.get('node', {})
                                    variants.append({
                                        'id': var_node.get('id'),
                                        'title': var_node.get('title'),
                                        'price': var_node.get('price'),
                                        'image_url': var_node.get('image', {}).get('url') if var_node.get('image') else None
                                    })
                            products.append({
                                'id': node.get('id'),
                                'title': node.get('title'),
                                'descriptionHtml': node.get('descriptionHtml'),
                                'featuredImage_url': node.get('featuredImage', {}).get('url') if node.get('featuredImage') else None,
                                'variants': variants
                            })
                else:
                    logger.info(f"No products found or error in search for term: '{search_term}'")
            else:
                logger.info("Empty search term provided.")
        
        elif 'add_to_cart' in request.form:
            variant_id = request.form.get('variant_id')
            product_title = request.form.get('product_title', 'Unknown Product')
            variant_title = request.form.get('variant_title', '')
            price = request.form.get('price', '0.00') # For $0 orders, this will be 0
            quantity = int(request.form.get('quantity', 1))

            if variant_id:
                item_key = variant_id
                if item_key in cart:
                    cart[item_key]['quantity'] += quantity
                else:
                    cart[item_key] = {
                        'product_title': product_title,
                        'variant_title': variant_title,
                        'price': price, # Store price, even if it's 0
                        'quantity': quantity,
                        'variant_id': variant_id
                    }
                session['cart'] = cart
                logger.info(f"Added to cart: Variant ID {variant_id}, Qty: {quantity}. Cart: {cart}")
            # After adding to cart, we might want to re-display the page, potentially with the same search results
            # For simplicity, we'll just re-render the template. If search_term was POSTed, it won't persist unless handled.
            # For now, let's keep it simple and re-render.
            search_term = request.form.get('previous_search_term', '') # Try to retain search term

        elif 'remove_from_cart' in request.form:
            variant_id_to_remove = request.form.get('variant_id')
            if variant_id_to_remove in cart:
                del cart[variant_id_to_remove]
                session['cart'] = cart
                logger.info(f"Removed from cart: Variant ID {variant_id_to_remove}. Cart: {cart}")
            search_term = request.form.get('previous_search_term', '')

    # Prepare cart items for display
    cart_items_display = []
    total_cart_value = 0.0 # This will be 0 for $0 orders
    for item_id, item_details in cart.items():
        cart_items_display.append(item_details)
        # total_cart_value += float(item_details['price']) * item_details['quantity'] # For $0 orders, price is 0

    return render_template('products.html', 
                           shop_url=shop_url, 
                           products=products, 
                           search_term=search_term,
                           cart_items=cart_items_display,
                           total_cart_value=total_cart_value,
                           countries=countries) # Pass countries to the template


@app.route('/create-order', methods=['POST']) # Renamed route
def create_order(): # Renamed function
    logger.info("Accessing create_order route.")
    shop_url = session.get('shop_url')
    access_token = session.get('access_token')
    cart = session.get('cart', {})

    if not shop_url or not access_token:
        logger.warning("User not authenticated or session expired. Redirecting to connect.")
        return redirect(url_for('connect_store'))

    if not cart:
        logger.warning("Cart is empty. Cannot create order.")
        return redirect(url_for('product_search_page'))

    email = request.form.get('email')
    shipping_address_input = {
        "firstName": request.form.get('firstName'),
        "lastName": request.form.get('lastName'),
        "address1": request.form.get('address1'),
        "address2": request.form.get('address2'),
        "city": request.form.get('city'),
        "province": request.form.get('province'),
        "countryCode": request.form.get('country'), # Shopify uses countryCode (e.g., "US")
        "zip": request.form.get('zip'),
        "phone": request.form.get('phone')
    }

    # Get tags from form and process them
    tags_string = request.form.get('tags')
    tags_list = [tag.strip() for tag in tags_string.split(',') if tag.strip()] if tags_string else []

    mandatory_fields = {
        "email": email,
        "firstName": shipping_address_input["firstName"],
        "lastName": shipping_address_input["lastName"],
        "address1": shipping_address_input["address1"],
        "city": shipping_address_input["city"],
        "countryCode": shipping_address_input["countryCode"],
        "zip": shipping_address_input["zip"]
    }
    missing_fields = [key for key, value in mandatory_fields.items() if not value]
    if missing_fields:
        logger.error(f"Missing mandatory address fields: {', '.join(missing_fields)}")
        return f"Error: Missing mandatory address fields: {', '.join(missing_fields)}. Please go back and fill them.", 400

    line_items_input = []
    for item_id, item_details in cart.items():
        line_items_input.append({
            "variantId": item_details['variant_id'],
            "quantity": item_details['quantity']
        })
    
    draft_order_input = {
        "email": email,
        "lineItems": line_items_input,
        "shippingAddress": shipping_address_input,
        "note": "Order placed via Hypothesis app with 100% discount.",
        "customAttributes": [
            {"key": "OrderSource", "value": "HypothesisApp"},
            {"key": "PromotionDetails", "value": "100% Discount Applied"}
        ],
        "appliedDiscount": {
            "valueType": "PERCENTAGE",
            "value": 100.0,
            "title": "100% Hypothesis App Discount"
        },
        "useCustomerDefaultAddress": False # We are providing a shipping address
        # financialStatus will be determined upon completion
    }

    # Add tags to draft_order_input if available
    if tags_list:
        draft_order_input["tags"] = tags_list

    draft_order_create_mutation = """
    mutation draftOrderCreate($input: DraftOrderInput!) {
      draftOrderCreate(input: $input) {
        draftOrder {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    logger.info(f"Creating draft order for {shop_url} with input: {draft_order_input}")
    
    try:
        # Step 1: Create Draft Order
        draft_order_response_data = shopify_client.make_graphql_request(
            shop_url, access_token, draft_order_create_mutation, {"input": draft_order_input}
        )
        logger.info(f"Draft order creation response: {draft_order_response_data}")

        draft_order_create_result = draft_order_response_data.get("data", {}).get("draftOrderCreate", {})
        user_errors_draft = draft_order_create_result.get("userErrors")
        if user_errors_draft:
            error_messages = [f"{err.get('field', 'N/A')}: {err.get('message', 'Unknown error')}" for err in user_errors_draft]
            logger.error(f"User errors on draft order creation: {error_messages}")
            return f"Error creating draft order: {', '.join(error_messages)}", 400

        draft_order_details = draft_order_create_result.get("draftOrder")
        if not draft_order_details or not draft_order_details.get("id"):
            logger.error(f"Failed to create draft order or missing draft order ID. Response: {draft_order_response_data}")
            return "Failed to create draft order.", 500

        draft_order_id = draft_order_details["id"]
        logger.info(f"Draft order created successfully with ID: {draft_order_id}")

        # Step 2: Complete Draft Order (marking as paid since it's 100% discounted)
        draft_order_complete_payload = {
            "id": draft_order_id,
            "paymentPending": False # Since total should be $0, this marks it as paid
        }
        draft_order_complete_mutation = """
        mutation draftOrderComplete($id: ID!, $paymentPending: Boolean) {
          draftOrderComplete(id: $id, paymentPending: $paymentPending) {
            draftOrder {
              id # DraftOrder GID
              order { # The actual Order object
                id # Order GID
                name
                legacyResourceId
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        logger.info(f"Completing draft order for ID: {draft_order_id}")
        order_response_data = shopify_client.make_graphql_request(
            shop_url, access_token, draft_order_complete_mutation, draft_order_complete_payload
        )
        logger.info(f"Draft order complete response: {order_response_data}")

        draft_order_complete_result = order_response_data.get("data", {}).get("draftOrderComplete", {})
        user_errors_complete = draft_order_complete_result.get("userErrors")
        if user_errors_complete:
            error_messages = [f"{err.get('field', 'N/A')}: {err.get('message', 'Unknown error')}" for err in user_errors_complete]
            logger.error(f"User errors on draft order completion: {error_messages}")
            # Potentially delete the created draft order here if completion fails critically
            return f"Error completing order from draft: {', '.join(error_messages)}", 400
        
        # Extract order details from the 'order' field nested within 'draftOrder'
        completed_draft_order_node = draft_order_complete_result.get("draftOrder", {})
        order_details = completed_draft_order_node.get("order")

        if order_details and order_details.get('id'):
            order_id_gid = order_details.get('id')
            order_name = order_details.get('name')
            logger.info(f"Order created successfully from draft: ID {order_id_gid}, Name: {order_name}")
            session.pop('cart', None) # Clear the cart
            return redirect(url_for('view_order_status', order_id_param=order_id_gid.split('/')[-1]))
        else:
            logger.error(f"Order completion response did not contain final order details or ID. Response: {order_response_data}")
            # Potentially delete the created draft order here
            return "Failed to create order: No final order details returned after draft completion.", 500

    except Exception as e:
        logger.error(f"Exception during order creation via draft order: {e}", exc_info=True)
        return f"An error occurred during order creation: {e}", 500

# Renamed route and parameter for real orders
@app.route('/order-status/<order_id_param>')
def view_order_status(order_id_param):
    logger.info(f"Accessing view_order_status for order_id_param: {order_id_param}")
    shop_url = session.get('shop_url')
    access_token = session.get('access_token')

    if not shop_url or not access_token:
        logger.warning("User not authenticated or session expired. Redirecting to connect.")
        return redirect(url_for('connect_store'))

    # Construct the full Order GID
    # Example GID: "gid://shopify/Order/1234567890"
    order_gid = f"gid://shopify/Order/{order_id_param}"
    logger.info(f"Constructed Order GID: {order_gid}")

    order_data = get_order_details(shop_url, access_token, order_gid) # Call the function within app.py

    return render_template('order_status.html', order_data=order_data, shop_url=shop_url)

def get_order_details(shop_url: str, access_token: str, order_gid: str):
    """
    Fetches details for a specific real order using GraphQL.
    This function is defined within app.py and uses shopify_client.make_graphql_request.
    """
    logger.info(f"Fetching details for order GID: {order_gid} on shop: {shop_url} using app.py's get_order_details")
    query = """
    query getOrder($id: ID!) {
      order(id: $id) {
        id
        name
        legacyResourceId
        email
        createdAt
        updatedAt
        displayFinancialStatus
        displayFulfillmentStatus
        app { # Assuming app might have an 'id' or 'name' for display
          id
          name # Or 'name', depending on what's available
        }
        cancellation { # Assuming cancellation might have details
            # reason
            staffNote
            # Add other relevant cancellation subfields if needed
        }
        cancelledAt 
        cancelReason
        confirmed
        closed
        # discountApplications(first: 5) { # Fetch first 5 discount applications
        #     edges {
        #         node {
        #             allocationMethod
        #             targetSelection
        #             targetType
        #             value {
        #                 __typename
        #                 ... on MoneyV2 {
        #                     amount
        #                     currencyCode
        #                 }
        #                 ... on PricingPercentageValue {
        #                     percentage
        #                 }
        #             }
        #             title # If available, or use 'description'
        #         }
        #     }
        # }
        discountCode
        totalPriceSet {
          presentmentMoney {
            amount
            currencyCode
          }
        }
        lineItems(first: 10) {
          edges {
            node {
              title
              quantity
              variantTitle
              originalUnitPriceSet {
                 presentmentMoney {
                    amount
                    currencyCode
                }
              }
            }
          }
        }
        shippingAddress {
          firstName
          lastName
          address1
          address2
          city
          zip
          country
          province
          phone
        }
        note
        tags
        fulfillments(first: 5) { 
          id
          status
          deliveredAt
          displayStatus
          trackingInfo { 
            url
            company
            number
          }
        }
      }
    }
    """
    variables = {"id": order_gid}
    try:
        # Ensure this calls the make_graphql_request from the shopify_client module
        response_data = shopify_client.make_graphql_request(shop_url, access_token, query, variables)
        if response_data.get("data") and response_data["data"].get("order"):
            order_data = response_data["data"]["order"]
            logger.info(f"Successfully fetched order details for {order_gid} via app.py's get_order_details. Data: {order_data}") # Added log for the full response
            return order_data
        elif response_data.get("errors"):
            logger.error(f"GraphQL errors fetching order {order_gid} via app.py: {response_data['errors']}")
            return None
        else:
            logger.warning(f"No order data found or unexpected response for {order_gid} via app.py. Response: {response_data}")
            return None
    except Exception as e:
        logger.error(f"Error fetching order {order_gid} via app.py: {e}", exc_info=True)
        return None


if __name__ == '__main__':
    logger.info("Starting Flask application.") # Added
    # For development, Shopify requires HTTPS for callbacks.
    # Use ngrok: `ngrok http 5000` and update your app's URL in Shopify Partner Dashboard.
    # Then run your Flask app.
    app.run(debug=True, port=5000)