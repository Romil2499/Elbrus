# EL BRUSTO — Flask Ordering + Order Tracking

## Included features
- Existing EL BRUSTO customer-facing menu and design
- Email OTP registration through Gmail SMTP
- Login/logout, profile and server-side cart
- Checkout confirmation closes cleanly after DONE and resets the checkout modal for the next visit
- Gmail OTP on every customer login (5-minute expiry, maximum 5 attempts, resend option)
- Customer **MY ORDERS** button showing items, totals, current status and estimated delivery
- Separate `/admin` page with a protected admin sign-in
- Collapsible admin orders: customer name/status only until an order is clicked
- Admin dashboard charts and counts for today, the last 7 weeks, and the last 6 months, including recorded revenue
- Downloadable CSV order backup for Excel
- Inventory page to add/edit/remove stock quantities
- SQLite schema migration adds tracking columns without deleting existing orders
- Secret-free `.env.example` starter file

## Windows setup
1. Extract this ZIP to a normal folder.
2. Open PowerShell in the `EL_BRUSTO_Fixed` folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv venv
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
5. Edit `.env` and set:
   - `SECRET_KEY` to a long random value
   - `MAIL_USERNAME` to your full Gmail address
   - `MAIL_PASSWORD` to your Google-generated App Password (remove display spaces)
   - `ADMIN_USERNAME` and `ADMIN_PASSWORD` to a new, unique admin login
6. Start the website:
   ```powershell
   python app.py
   ```
7. Customer website: http://127.0.0.1:5000
8. Admin order dashboard: http://127.0.0.1:5000/admin

## Customer flow
1. Register and verify the email OTP.
2. Add menu items to the cart and open CHECK OUT.
3. Place the order. The DONE confirmation appears only after the server saves the order.
4. Open MY ORDERS to track status and the delivery schedule.
7. Admin signs in at `/admin`, clicks a customer name to expand order details, updates status/date/time/message, and saves. The customer sees saved updates under MY ORDERS.
8. The admin dashboard includes sales/order charts and a CSV backup download. Inventory quantities are currently managed manually from the Inventory section; enter actual counts and update them as stock changes.

## Important security and deployment notes
- This archive intentionally does not include `.env`, the SQLite database, or a virtual environment. This prevents private credentials and customer records from being distributed. The app creates a new `el_brusto.db` automatically on first start.
- If you need existing local accounts/orders, keep a separate backup of your existing `el_brusto.db` and copy it into this project before starting. The app migrates the old `orders` table by adding delivery tracking columns.
- Never upload `.env` or real credentials to GitHub. Do not use the development Flask server/debugger as a production server.
- For online hosting, use a production WSGI server, configure `SECRET_KEY`, admin credentials and Gmail settings as host environment variables, use HTTPS, and choose persistent storage or a managed database. SQLite on ephemeral hosting may lose data.
- Use a long unique admin password. The `/admin` page does not expose order data until admin login succeeds.
- Email OTP is enabled; phone number is collected for delivery contact. SMS OTP requires a separate Twilio configuration and is not part of this flow.


## Inventory note
The inventory screen starts product rows at zero because the app cannot know the shop’s real stock. Enter the actual stock counts in Admin → Inventory. The current inventory feature is a manual stock register and does not automatically deduct quantities when an order is placed.

## Latest order/admin behavior
- After a customer places an order, a success message appears and the checkout/cart overlays automatically close after about 2.5 seconds, returning the customer to the home page. They may choose Track My Order before the timeout.
- Customers can cancel their own order only while its status is `Pending` and within 5 minutes of its recorded creation time. The server enforces the limit; the countdown shown in My Orders is informational.
- The admin dashboard checks the existing server session on page load, so refreshing `/admin` should restore the dashboard while the session cookie remains available. Clicking Log out still ends the session.
- Admins can delete an order record from the expanded order details. This permanently removes that order and its line items from the active database and analytics. Download the CSV backup first if the record must be retained.
