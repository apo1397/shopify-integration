import requests
import os
import logging # Added

logger = logging.getLogger(__name__) # Added

def make_graphql_request(shop_url: str, access_token: str, query: str, variables: dict = None):
    """
    Makes a GraphQL request to the Shopify Admin API.
    """
    # Be cautious about logging full queries or variables if they contain sensitive PII.
    # For debugging, you might log parts or indicate their presence.
    log_variables = bool(variables) # Log if variables are present, not their content directly for security
    logger.info(f"Making GraphQL request to {shop_url}. Query: <{query[:50]}...>, Variables present: {log_variables}") # Added

    headers = {
        "X-Shopify-Access-Token": access_token, # Sensitive: Do not log the token itself
        "Content-Type": "application/json",
    }
    # Use the API version from environment or a sensible default
    api_version = os.getenv('SHOPIFY_API_VERSION', '2024-04') # Updated default to a recent stable version
    graphql_url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
    logger.debug(f"GraphQL URL: {graphql_url}") # Added

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    try:
        response = requests.post(graphql_url, json=payload, headers=headers)
        logger.debug(f"Shopify API response status: {response.status_code} for {shop_url}") # Added
        response.raise_for_status()  # Raises an exception for HTTP errors
        response_json = response.json()
        if 'errors' in response_json:
            logger.warning(f"GraphQL request to {shop_url} returned errors: {response_json['errors']}") # Added
        return response_json
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while calling Shopify API for {shop_url}: {http_err} - Response: {response.text}", exc_info=True) # Added
        raise # Re-raise the exception after logging
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request exception occurred while calling Shopify API for {shop_url}: {req_err}", exc_info=True) # Added
        raise # Re-raise the exception after logging
    except Exception as e:
        logger.error(f"An unexpected error occurred in make_graphql_request for {shop_url}: {e}", exc_info=True) # Added
        raise # Re-raise the exception

def search_products(shop_url: str, access_token: str, search_query: str, num_products: int = 10, cursor: str = None):
    """
    Searches for products in the Shopify store using GraphQL, with pagination support.
    """
    logger.info(f"Searching products for shop: {{shop_url}} with query: '{{search_query}}', cursor: {{cursor}}")
    # Added cursor to the GraphQL query variables and products query arguments
    # Added hasPreviousPage, startCursor, endCursor to pageInfo
    query = """
    query searchProducts($searchQuery: String!, $numProducts: Int!, $cursor: String) {
      products(first: $numProducts, query: $searchQuery, after: $cursor) {
        edges {
          node {
            id
            title
            descriptionHtml
            onlineStoreUrl
            featuredImage {
              url
            }
            variants(first: 5) {
              edges {
                node {
                  id
                  title
                  price
                  image {
                    url
                  }
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          hasPreviousPage
          startCursor
          endCursor
        }
      }
    }
    """
    variables = {
        "searchQuery": search_query,
        "numProducts": num_products
    }
    if cursor:
        variables["cursor"] = cursor
    try:
        response_data = make_graphql_request(shop_url, access_token, query, variables)
        if response_data.get("data") and response_data["data"].get("products"):
            products_data = response_data["data"]["products"]
            products = products_data["edges"]
            page_info = products_data["pageInfo"]
            logger.info(f"Found {{len(products)}} products for query '{{search_query}}' on {{shop_url}}")

            # Return a dictionary containing both products and pageInfo
            return {"products": products, "pageInfo": page_info}
        else:
            logger.warning(f"No products found or unexpected response structure for query '{{search_query}}' on {{shop_url}}. Response: {{response_data}}")
            # Return empty products list and pageInfo dictionary in case of no data or error
            return {"products": [], "pageInfo": {"hasNextPage": False, "hasPreviousPage": False, "startCursor": None, "endCursor": None}}
    except Exception as e:
        logger.error(f"Error searching products on {{shop_url}} with query '{{search_query}}': {{e}}", exc_info=True)
        # Return empty products list and pageInfo dictionary in case of an exception
        return {"products": [], "pageInfo": {"hasNextPage": False, "hasPreviousPage": False, "startCursor": None, "endCursor": None}}

def get_draft_order_details(shop_url: str, access_token: str, draft_order_gid: str):
    """
    Fetches details for a specific draft order using GraphQL.
    """
    logger.info(f"Fetching details for draft order GID: {draft_order_gid} on shop: {shop_url}")
    query = """
    query getDraftOrder($id: ID!) {
      draftOrder(id: $id) {
        id
        name
        status # e.g., OPEN, INVOICE_SENT, COMPLETED
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
        email
        # If the draft order is completed, this field will contain the actual order
        order {
          id
          name
          legacyResourceId # Useful for linking to Shopify admin
          displayFinancialStatus
          displayFulfillmentStatus
        }
        invoiceUrl # URL to the invoice if sent
        completedAt
      }
    }
    """
    variables = {"id": draft_order_gid}
    try:
        response_data = make_graphql_request(shop_url, access_token, query, variables)
        if response_data.get("data") and response_data["data"].get("draftOrder"):
            draft_order = response_data["data"]["draftOrder"]
            logger.info(f"Successfully fetched draft order details for {draft_order_gid}")
            return draft_order
        elif response_data.get("errors"):
            logger.error(f"GraphQL errors fetching draft order {draft_order_gid}: {response_data['errors']}")
            return None
        else:
            logger.warning(f"No draft order data found or unexpected response for {draft_order_gid}. Response: {response_data}")
            return None
    except Exception as e:
        logger.error(f"Error fetching draft order {draft_order_gid}: {e}", exc_info=True)
        return None

def get_order_details(shop_url: str, access_token: str, order_gid: str):
    """
    Fetches details for a specific real order using GraphQL.
    """
    logger.info(f"Fetching details for order GID: {order_gid} on shop: {shop_url}")
    query = """
    query getOrder($id: ID!) {
      order(id: $id) {
        id
        name
        legacyResourceId
        app
        email
        createdAt
        displayFinancialStatus
        displayFulfillmentStatus 
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
        fulfillments(first: 5) { # Returns a list of Fulfillment objects
          id
          status 
          deliveredAt 
          displayStatus 
          trackingInfo { # Returns a list of FulfillmentTrackingInfo objects
            url 
            company
            number
          }
        }
        # Add any other order fields you need
      }
    }
    """
    variables = {"id": order_gid}
    try:
        response_data = make_graphql_request(shop_url, access_token, query, variables)
        if response_data.get("data") and response_data["data"].get("order"):
            order_data = response_data["data"]["order"]
            logger.info(f"Successfully fetched order details for {order_gid}")
            return order_data
        elif response_data.get("errors"):
            logger.error(f"GraphQL errors fetching order {order_gid}: {response_data['errors']}")
            return None
        else:
            logger.warning(f"No order data found or unexpected response for {order_gid}. Response: {response_data}")
            return None
    except Exception as e:
        logger.error(f"Error fetching order {order_gid}: {e}", exc_info=True)
        return None