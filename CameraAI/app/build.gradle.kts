plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.parcelize)
    alias(libs.plugins.kotlin.serialization)
}


android {
    namespace = "com.example.cameraai"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.example.cameraai"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Supabase config
        buildConfigField("String", "SUPABASE_URL",  "\"https://hfnyjmdloozduyrlgnht.supabase.co\"")
        buildConfigField("String", "SUPABASE_ANON", "\"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhmbnlqbWRsb296ZHV5cmxnbmh0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Mzk1MTI4MTMsImV4cCI6MjA1NTA4ODgxM30.lYK_k2kCvqIDj8PGFC3k95DNoB6_M6TDY1qdnbcmZxs\"")
        buildConfigField("String", "STORAGE_BUCKET","\"Camera AI\"")
        buildConfigField("String", "SEPAY_TOKEN",   "\"your_sepay_access_token_here\"")
        buildConfigField("String", "BANK_ACCOUNT",  "\"0332282868\"")
        buildConfigField("String", "BANK_BIN",      "\"970422\"")
        buildConfigField("String", "BANK_NAME",     "\"MB\"")
    }

    buildFeatures {
        viewBinding = true
        buildConfig  = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlinOptions {
        jvmTarget = "11"
    }
}

dependencies {
    // AndroidX
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.fragment:fragment-ktx:1.8.5")
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("androidx.viewpager2:viewpager2:1.1.0")

    // Supabase
    implementation(platform("io.github.jan-tennant.supabase:bom:2.7.2"))
    implementation("io.github.jan-tennant.supabase:postgrest-kt")
    implementation("io.github.jan-tennant.supabase:storage-kt")

    // Ktor engine for Supabase
    implementation("io.ktor:ktor-client-android:2.3.12")
    implementation("io.ktor:ktor-client-okhttp:2.3.12")

    // Image loading
    implementation("com.github.bumptech.glide:glide:4.16.0")

    // HTTP (SePay API)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // QR code display
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // JSON
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

    // PhotoView (zoom ảnh vi phạm)
    implementation("com.github.chrisbanes:PhotoView:2.3.0")

    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.espresso:espresso-core:3.6.1")
}