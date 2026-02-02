# Mobile App (Android) - Architecture & Features

## 🎯 Mục Đích

Mobile app cho người dùng để:
- **Tra cứu vi phạm** bằng biển số xe
- Xem chi tiết vi phạm (ảnh, thời gian, địa điểm)
- Nhận thông báo khi có vi phạm mới (future)
- Thanh toán phạt online (future)

---

## 📐 App Structure

```
(Future: iOS)

Android App (Kotlin/Java)
├─ Screens:
│  ├─ LoginScreen           # Đăng nhập bằng biển số
│  ├─ ViolationListScreen   # Danh sách vi phạm
│  ├─ ViolationDetailScreen # Chi tiết 1 vi phạm
│  └─ SettingsScreen        # Cài đặt (future)
│
├─ Services:
│  ├─ ApiService            # HTTP client (Retrofit)
│  ├─ NotificationService   # Push notifications (FCM)
│  └─ StorageService        # Local cache (Room)
│
└─ Utils:
   ├─ ImageLoader           # Load ảnh (Glide/Coil)
   └─ DateFormatter         # Format timestamp
```

---

## 📱 Screen 1: Login / Lookup

### UI Layout

```
┌─────────────────────────────────────┐
│                                     │
│         🚦 TRAFFIC LOOKUP           │
│                                     │
│     Check Your Violations           │
│                                     │
│  ┌────────────────────────────────┐ │
│  │ License Plate                  │ │
│  │ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │ │
│  │ ┃ 51F-12345                  ┃ │ │
│  │ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │ │
│  │                                │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌────────────────────────────────┐ │
│  │     🔍 CHECK VIOLATIONS        │ │
│  └────────────────────────────────┘ │
│                                     │
│  Sample: 51F12345, 29B98765        │
│                                     │
└─────────────────────────────────────┘
```

### Code Example (Kotlin)

```kotlin
// LoginScreen.kt
class LoginScreen : ComponentActivity() {
    private val viewModel: ViolationViewModel by viewModels()
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            TrafficLookupTheme {
                LoginContent()
            }
        }
    }
    
    @Composable
    fun LoginContent() {
        var licensePlate by remember { mutableStateOf("") }
        var isLoading by remember { mutableStateOf(false) }
        
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // Logo
            Image(
                painter = painterResource(R.drawable.ic_traffic_light),
                contentDescription = "Logo",
                modifier = Modifier.size(120.dp)
            )
            
            Spacer(modifier = Modifier.height(32.dp))
            
            Text(
                text = "TRAFFIC LOOKUP",
                style = MaterialTheme.typography.h4,
                fontWeight = FontWeight.Bold
            )
            
            Spacer(modifier = Modifier.height(8.dp))
            
            Text(
                text = "Check Your Violations",
                style = MaterialTheme.typography.body1,
                color = Color.Gray
            )
            
            Spacer(modifier = Modifier.height(32.dp))
            
            // Input
            OutlinedTextField(
                value = licensePlate,
                onValueChange = { licensePlate = it.uppercase() },
                label = { Text("License Plate") },
                placeholder = { Text("51F-12345") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Characters
                )
            )
            
            Spacer(modifier = Modifier.height(24.dp))
            
            // Button
            Button(
                onClick = {
                    isLoading = true
                    viewModel.fetchViolations(licensePlate)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                enabled = licensePlate.isNotBlank() && !isLoading
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        color = Color.White,
                        modifier = Modifier.size(24.dp)
                    )
                } else {
                    Text("🔍 CHECK VIOLATIONS")
                }
            }
        }
        
        // Observer
        val violations by viewModel.violations.collectAsState()
        violations?.let {
            // Navigate to list screen
            navigateToList(licensePlate)
        }
    }
}
```

### API Call

**Endpoint**: `GET /api/violations/by-plate/{plate}`

```kotlin
interface ApiService {
    @GET("/api/violations/by-plate/{plate}")
    suspend fun getViolationsByPlate(
        @Path("plate") licensePlate: String
    ): Response<ViolationListResponse>
}

data class ViolationListResponse(
    val license_plate: String,
    val total_violations: Int,
    val violations: List<Violation>
)

data class Violation(
    val id: Int,
    val license_plate: String,
    val camera_name: String,
    val location: String,
    val latitude: Double,
    val longitude: Double,
    val timestamp: String,
    val full_image_url: String,
    val cropped_plate_url: String,
    val confidence: Float,
    val vote_count: Int,
    val vote_percent: Float,
    val quality_score: Float
)
```

---

## 📋 Screen 2: Violation List

### UI Layout

```
┌─────────────────────────────────────┐
│ ◄  51F-12345      🔔 Settings       │
├─────────────────────────────────────┤
│                                     │
│  Total: 5 violations                │
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📷 [Image]    Gò Vấp            ││
│  │               Ngã tư GV          ││
│  │               02/02 10:15:30     ││
│  │               [View Details →]   ││
│  └─────────────────────────────────┘│
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📷 [Image]    Củ Chi            ││
│  │               Ngã tư 22/12       ││
│  │               02/01 14:20:45     ││
│  │               [View Details →]   ││
│  └─────────────────────────────────┘│
│                                     │
│  ┌─────────────────────────────────┐│
│  │ 📷 [Image]    Hà Nội            ││
│  │               Láng Hạ - Thái Hà ││
│  │               01/28 08:05:12     ││
│  │               [View Details →]   ││
│  └─────────────────────────────────┘│
│                                     │
└─────────────────────────────────────┘
```

### Code Example

```kotlin
@Composable
fun ViolationListScreen(
    licensePlate: String,
    violations: List<Violation>
) {
    Column(modifier = Modifier.fillMaxSize()) {
        // Header
        TopAppBar(
            title = { Text(licensePlate) },
            navigationIcon = {
                IconButton(onClick = { /* Navigate back */ }) {
                    Icon(Icons.Default.ArrowBack, "Back")
                }
            },
            actions = {
                IconButton(onClick = { /* Open settings */ }) {
                    Icon(Icons.Default.Notifications, "Notifications")
                }
            }
        )
        
        // Summary
        Text(
            text = "Total: ${violations.size} violations",
            modifier = Modifier.padding(16.dp),
            style = MaterialTheme.typography.h6
        )
        
        // List
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            items(violations) { violation ->
                ViolationCard(violation = violation) {
                    // Navigate to detail
                    navigateToDetail(violation.id)
                }
            }
        }
    }
}

@Composable
fun ViolationCard(
    violation: Violation,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = 4.dp
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Thumbnail
            AsyncImage(
                model = violation.full_image_url,
                contentDescription = "Violation image",
                modifier = Modifier
                    .size(80.dp)
                    .clip(RoundedCornerShape(8.dp)),
                contentScale = ContentScale.Crop
            )
            
            // Info
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = violation.camera_name,
                    style = MaterialTheme.typography.subtitle1,
                    fontWeight = FontWeight.Bold
                )
                
                Text(
                    text = violation.location,
                    style = MaterialTheme.typography.body2,
                    color = Color.Gray
                )
                
                Text(
                    text = formatTimestamp(violation.timestamp),
                    style = MaterialTheme.typography.caption,
                    color = Color.Gray
                )
            }
            
            // Arrow
            Icon(
                Icons.Default.ArrowForward,
                contentDescription = "View",
                tint = Color.Gray
            )
        }
    }
}
```

---

## 🔍 Screen 3: Violation Detail

### UI Layout

```
┌─────────────────────────────────────┐
│ ◄  Back                             │
├─────────────────────────────────────┤
│                                     │
│  📷 FULL IMAGE                      │
│  ┌─────────────────────────────────┐│
│  │                                 ││
│  │     [Full size image]           ││
│  │                                 ││
│  └─────────────────────────────────┘│
│  [🔍 View Full Screen]              │
│                                     │
│  📷 CROPPED PLATE                   │
│  ┌──────────────┐                  │
│  │ [Plate crop] │                  │
│  └──────────────┘                  │
│                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                     │
│  📝 DETAILS                         │
│                                     │
│  License Plate:  51F-12345          │
│  Confidence:     92.5% ⭐⭐⭐⭐⭐    │
│  Quality:        88.2/100 ⭐⭐⭐⭐   │
│                                     │
│  📍 LOCATION                        │
│  Camera:         Gò Vấp (#1)        │
│  Address:        Ngã tư Gò Vấp      │
│  Coordinates:    10.8231, 106.6297  │
│  [📍 View on Map]                   │
│                                     │
│  🕐 TIME                            │
│  Timestamp:      Feb 02, 2026       │
│                  10:15:30 AM        │
│                                     │
│  🚦 VIOLATION                       │
│  Type:           Red Light Violation│
│  Status:         🔴 Pending         │
│                                     │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                     │
│  [💳 PAY FINE] (Future)             │
│                                     │
└─────────────────────────────────────┘
```

### Code Example

```kotlin
@Composable
fun ViolationDetailScreen(
    violationId: Int,
    viewModel: ViolationViewModel
) {
    val violation by viewModel.getViolationDetail(violationId).collectAsState()
    
    violation?.let { detail ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
        ) {
            // Header
            TopAppBar(
                title = { Text("Violation #${detail.id}") },
                navigationIcon = {
                    IconButton(onClick = { /* Back */ }) {
                        Icon(Icons.Default.ArrowBack, "Back")
                    }
                }
            )
            
            // Full Image
            ImageSection(
                title = "FULL IMAGE",
                imageUrl = detail.full_image_url
            )
            
            // Cropped Plate
            ImageSection(
                title = "LICENSE PLATE",
                imageUrl = detail.cropped_plate_url,
                modifier = Modifier.height(120.dp)
            )
            
            Divider(modifier = Modifier.padding(vertical = 16.dp))
            
            // Details
            DetailRow(icon = "📝", label = "License Plate", value = detail.license_plate)
            DetailRow(icon = "⭐", label = "Confidence", value = "${detail.confidence}%")
            DetailRow(icon = "📊", label = "Quality", value = "${detail.quality_score}/100")
            
            Divider(modifier = Modifier.padding(vertical = 16.dp))
            
            // Location
            DetailRow(icon = "📍", label = "Camera", value = detail.camera_name)
            DetailRow(icon = "🗺️", label = "Location", value = detail.location)
            
            Button(
                onClick = { openMap(detail.latitude, detail.longitude) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
            ) {
                Text("📍 View on Map")
            }
            
            Divider(modifier = Modifier.padding(vertical = 16.dp))
            
            // Time
            DetailRow(icon = "🕐", label = "Timestamp", value = formatTimestamp(detail.timestamp))
            
            Divider(modifier = Modifier.padding(vertical = 16.dp))
            
            // Violation Info
            DetailRow(icon = "🚦", label = "Type", value = detail.violation_type)
            DetailRow(icon = "⚠️", label = "Status", value = "Pending Payment")
            
            // Pay Button (Future)
            Button(
                onClick = { /* Pay */ },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
                    .height(56.dp),
                colors = ButtonDefaults.buttonColors(backgroundColor = Color.Red)
            ) {
                Text("💳 PAY FINE", color = Color.White, fontSize = 18.sp)
            }
        }
    }
}

@Composable
fun ImageSection(
    title: String,
    imageUrl: String,
    modifier: Modifier = Modifier
) {
    Column(modifier = Modifier.padding(16.dp)) {
        Text(
            text = title,
            style = MaterialTheme.typography.subtitle2,
            color = Color.Gray
        )
        Spacer(modifier = Modifier.height(8.dp))
        AsyncImage(
            model = imageUrl,
            contentDescription = title,
            modifier = modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp)),
            contentScale = ContentScale.Crop
        )
    }
}

@Composable
fun DetailRow(icon: String, label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row {
            Text(text = icon, fontSize = 20.sp)
            Spacer(modifier = Modifier.width(8.dp))
            Text(text = label, color = Color.Gray)
        }
        Text(text = value, fontWeight = FontWeight.Bold)
    }
}
```

---

## 🔔 Future Features

### 1. Push Notifications (Firebase Cloud Messaging)

```kotlin
class FirebaseMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        // New violation notification
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic rưởi_traffic)
            .setContentTitle("New Violation")
            .setContentText("You have a new traffic violation")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        
        notificationManager.notify(1, notification)
    }
}
```

**Backend**: Send FCM when new violation created
```python
# backend/services/notification_service.py
import firebase_admin
from firebase_admin import messaging

def send_violation_notification(license_plate: str, violation_id: int):
    # Get user FCM token from database
    user = db.users.find_one({"license_plate": license_plate})
    
    if user and user.get("fcm_token"):
        message = messaging.Message(
            notification=messaging.Notification(
                title="New Violation",
                body=f"You have a new traffic violation at {location}"
            ),
            token=user["fcm_token"]
        )
        
        messaging.send(message)
```

### 2. Payment Integration (Momo/ZaloPay/VNPay)

```kotlin
fun initiatePayment(violationId: Int, amount: Int) {
    // Call backend to create payment URL
    apiService.createPayment(violationId, amount)
        .enqueue(object : Callback<PaymentResponse> {
            override fun onResponse(...) {
                // Open payment URL in WebView
                openPaymentWebView(response.payment_url)
            }
        })
}
```

### 3. User Account & History

- Register account (phone + OTP)
- Link multiple license plates
- Payment history
- Appeal violations

---

## 📦 Tech Stack

### Android (Kotlin)

- **UI**: Jetpack Compose
- **Networking**: Retrofit + OkHttp
- **Image Loading**: Coil
- **DI**: Hilt
- **Async**: Coroutines + Flow
- **Local DB**: Room
- **Notifications**: Firebase Cloud Messaging

### Dependencies (`build.gradle`)

```gradle
dependencies {
    // Jetpack Compose
    implementation "androidx.compose.ui:ui:1.5.0"
    implementation "androidx.compose.material:material:1.5.0"
    
    // Networking
    implementation "com.squareup.retrofit2:retrofit:2.9.0"
    implementation "com.squareup.retrofit2:converter-gson:2.9.0"
    
    // Image Loading
    implementation "io.coil-kt:coil-compose:2.4.0"
    
    // DI
    implementation "com.google.dagger:hilt-android:2.48"
    
    // Firebase
    implementation "com.google.firebase:firebase-messaging:23.2.0"
}
```

---

## 🚀 Backend API Requirements

### New Endpoints

```
GET  /api/violations/by-plate/{plate}
POST /api/users/register                (Future)
POST /api/users/login                   (Future)
POST /api/payments/create               (Future)
GET  /api/payments/{id}/status          (Future)
```

## ✅ Features Summary

- ✅ Simple login by license plate
- ✅ List all violations
- ✅ View violation details (images, location, time)
- ✅ Map integration
- [ ] Push notifications (future)
- [ ] Payment integration (future)
- [ ] User accounts (future)
- [ ] Appeal violations (future)

---

**Platform**: Android (Kotlin + Jetpack Compose)  
**Future**: iOS (SwiftUI)
