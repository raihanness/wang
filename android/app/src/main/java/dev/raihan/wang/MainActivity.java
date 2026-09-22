package dev.raihan.wang;

import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResult;
import androidx.activity.result.ActivityResultCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import android.content.res.Configuration;
import android.graphics.Color;
import android.view.Window;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends AppCompatActivity {

    private WebView mWebView;
    private SwipeRefreshLayout mSwipeRefresh;
    private ValueCallback<Uri[]> mFilePathCallback;
    private String mCameraPhotoPath;
    private Uri mCameraPhotoUri;
    private String mPendingCapturedPhotoBase64;
    private ActivityResultLauncher<Intent> mFileChooserLauncher;

    // Controls whether the current page and active DOM elements allow pull-to-refresh
    private volatile boolean mPageAllowsRefresh = true;
    private volatile boolean mIsScrollableActive = false;

    // Last recorded system bar insets in dp
    private int mLastTopInsetsDp = 0;
    private int mLastBottomInsetsDp = 0;

    public class WebAppInterface {
        @JavascriptInterface
        public void setPullToRefreshEnabled(boolean enabled) {
            mPageAllowsRefresh = enabled;
            runOnUiThread(() -> syncSwipeRefreshState());
        }

        @JavascriptInterface
        public void setScrollableActive(boolean active) {
            mIsScrollableActive = active;
            runOnUiThread(() -> syncSwipeRefreshState());
        }

        @JavascriptInterface
        public void setSystemTheme(boolean isDark) {
            runOnUiThread(() -> updateSystemBarIcons(isDark));
        }

        @JavascriptInterface
        public String getPendingCapturedPhoto() {
            String photo = mPendingCapturedPhotoBase64;
            mPendingCapturedPhotoBase64 = null;
            return photo != null ? photo : "";
        }

        @JavascriptInterface
        public void downloadUrl(String url) {
            runOnUiThread(() -> {
                if (mWebView != null) {
                    handleDownload(url, mWebView.getSettings().getUserAgentString(), null, "text/csv");
                }
            });
        }
    }

    private void updateSystemBarIcons(boolean isDark) {
        Window window = getWindow();
        WindowInsetsControllerCompat insetsController = WindowCompat.getInsetsController(window, window.getDecorView());
        if (insetsController != null) {
            // isAppearanceLightStatusBars(true) means dark icons (for light theme)
            // isAppearanceLightStatusBars(false) means white/light icons (for dark theme)
            insetsController.setAppearanceLightStatusBars(!isDark);
            insetsController.setAppearanceLightNavigationBars(!isDark);
        }
    }

    private void setupEdgeToEdgeInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.swipe_refresh), (v, windowInsets) -> {
            Insets insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars());
            float density = getResources().getDisplayMetrics().density;
            int topDp = Math.round(insets.top / density);
            int bottomDp = Math.round(insets.bottom / density);

            mLastTopInsetsDp = topDp;
            mLastBottomInsetsDp = bottomDp;

            injectSafeAreaInsets(topDp, bottomDp);
            return windowInsets;
        });
    }

    private void injectSafeAreaInsets(int topDp, int bottomDp) {
        if (mWebView != null && (topDp > 0 || bottomDp > 0)) {
            String js = "document.documentElement.style.setProperty('--safe-area-top', '" + topDp + "px');" +
                        "document.documentElement.style.setProperty('--safe-area-bottom', '" + bottomDp + "px');";
            mWebView.evaluateJavascript(js, null);
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Enable true Edge-to-Edge display with transparent system bars
        Window window = getWindow();
        WindowCompat.setDecorFitsSystemWindows(window, false);
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setStatusBarContrastEnforced(false);
            window.setNavigationBarContrastEnforced(false);
        }

        setContentView(R.layout.activity_main);

        // Initialize system bar icons based on current device night mode
        int nightMode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        updateSystemBarIcons(nightMode == Configuration.UI_MODE_NIGHT_YES);

        // Setup Edge-to-Edge window insets listening and CSS injection
        setupEdgeToEdgeInsets();

        mWebView = findViewById(R.id.web_view);
        mSwipeRefresh = findViewById(R.id.swipe_refresh);

        // Configure SwipeRefreshLayout with Wang pastel primary & accent colors
        mSwipeRefresh.setColorSchemeColors(
                getColor(R.color.primary),
                getColor(R.color.accent)
        );
        mSwipeRefresh.setOnRefreshListener(() -> mWebView.reload());

        // Fix scroll-to-refresh conflict:
        // 1. If the current view is a form (e.g. /new, /edit), pull-to-refresh is disabled to protect inputs.
        // 2. If a bottom sheet (e.g. Add/Edit Transaction sheet, Categories, Wallet Picker, Filters)
        //    is open or being touched, return true so SwipeRefreshLayout NEVER intercepts downward gestures.
        // 3. Otherwise, pull-to-refresh is only allowed when genuine scroll is at the top of the root page.
        mSwipeRefresh.setOnChildScrollUpCallback((parent, child) -> {
            if (!mPageAllowsRefresh || mIsScrollableActive) {
                return true; // Child can scroll or refresh is prevented -> do NOT intercept
            }
            return mWebView.canScrollVertically(-1) || mWebView.getScrollY() > 0;
        });

        mWebView.setOnScrollChangeListener((v, scrollX, scrollY, oldScrollX, oldScrollY) -> {
            syncSwipeRefreshState();
        });

        // Setup Modern Activity Result Launcher for Camera & File Uploads (Receipt Attachments)
        setupFileChooserLauncher();

        // Setup WebView settings and clients
        setupWebView();

        // Setup native Back navigation (WebView history before app exit)
        setupBackNavigation();

        // Load configured hosted domain URL
        String targetUrl = getString(R.string.app_web_url);
        if (savedInstanceState != null) {
            mWebView.restoreState(savedInstanceState);
            mCameraPhotoPath = savedInstanceState.getString("camera_photo_path");
            mPendingCapturedPhotoBase64 = savedInstanceState.getString("pending_photo_base64");
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                mCameraPhotoUri = savedInstanceState.getParcelable("camera_photo_uri", Uri.class);
            } else {
                mCameraPhotoUri = savedInstanceState.getParcelable("camera_photo_uri");
            }
        }
        if (mWebView.getUrl() == null) {
            mWebView.loadUrl(targetUrl);
        }
    }

    private void syncSwipeRefreshState() {
        boolean isAtTop = mWebView.getScrollY() == 0 && !mWebView.canScrollVertically(-1);
        boolean canRefresh = mPageAllowsRefresh && !mIsScrollableActive && isAtTop;
        mSwipeRefresh.setEnabled(canRefresh);
    }

    private boolean isPullToRefreshAllowedForUrl(String url) {
        if (url == null) return true;
        try {
            Uri uri = Uri.parse(url);
            String path = uri.getPath();
            if (path == null) return true;
            if (path.contains("/new") || path.contains("/edit") || path.contains("/delete")
                    || path.contains("/login") || path.contains("/signup")) {
                return false;
            }
        } catch (Exception ignored) {}
        return true;
    }

    private void setupWebView() {
        WebSettings webSettings = mWebView.getSettings();

        // Core web engine settings
        webSettings.setJavaScriptEnabled(true);
        webSettings.setDomStorageEnabled(true);
        webSettings.setDatabaseEnabled(true);
        webSettings.setAllowFileAccess(true);
        webSettings.setAllowContentAccess(true);

        // Enable hardware acceleration and audio without requiring user gesture tap
        webSettings.setMediaPlaybackRequiresUserGesture(false);

        // Cache & responsive viewport
        webSettings.setCacheMode(WebSettings.LOAD_DEFAULT);
        webSettings.setUseWideViewPort(true);
        webSettings.setLoadWithOverviewMode(true);
        webSettings.setSupportZoom(false);
        webSettings.setBuiltInZoomControls(false);
        webSettings.setDisplayZoomControls(false);

        // Identify as Wang Native Android wrapper in User-Agent header
        String customUA = webSettings.getUserAgentString() + " WangNativeAndroid/1.0.5";
        webSettings.setUserAgentString(customUA);

        // Persistent Cookies & Session management
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(mWebView, true);

        // Enable fast scroll physics and disable overscroll glow
        mWebView.setOverScrollMode(View.OVER_SCROLL_NEVER);

        // Register AndroidBridge JavaScript interface
        mWebView.addJavascriptInterface(new WebAppInterface(), "AndroidBridge");

        // Set DownloadListener for files (e.g. CSV Export)
        mWebView.setDownloadListener((url, userAgent, contentDisposition, mimetype, contentLength) -> {
            handleDownload(url, userAgent, contentDisposition, mimetype);
        });

        // Set WebViewClient
        mWebView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();

                if (scheme == null) return false;

                // Handle external protocols (tel, mailto, whatsapp, market, etc.)
                if (scheme.equalsIgnoreCase("tel") ||
                    scheme.equalsIgnoreCase("mailto") ||
                    scheme.equalsIgnoreCase("sms") ||
                    scheme.equalsIgnoreCase("whatsapp") ||
                    scheme.equalsIgnoreCase("intent")) {
                    try {
                        Intent intent = new Intent(Intent.ACTION_VIEW, uri);
                        startActivity(intent);
                        return true;
                    } catch (ActivityNotFoundException e) {
                        return true;
                    }
                }

                // Keep all HTTP / HTTPS navigation inside the WebView
                return false;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                super.onPageStarted(view, url, favicon);
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
            }

            @Override
            public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
                super.doUpdateVisitedHistory(view, url, isReload);
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
                injectSafeAreaInsets(mLastTopInsetsDp, mLastBottomInsetsDp);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                mSwipeRefresh.setRefreshing(false);
                CookieManager.getInstance().flush();
                mPageAllowsRefresh = isPullToRefreshAllowedForUrl(url);
                syncSwipeRefreshState();
                injectScrollHandler(view);
                injectSafeAreaInsets(mLastTopInsetsDp, mLastBottomInsetsDp);
                view.evaluateJavascript("document.documentElement.getAttribute('data-theme')", val -> {
                    if (val != null) {
                        updateSystemBarIcons(val.contains("dark"));
                    }
                });
                if (mPendingCapturedPhotoBase64 != null) {
                    view.postDelayed(() -> deliverPendingPhotoToWebView(), 400);
                }
            }

            @Override
            public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
                if (mWebView != null) {
                    ViewGroup parent = (ViewGroup) mWebView.getParent();
                    if (parent != null) {
                        parent.removeView(mWebView);
                    }
                    mWebView.destroy();
                    mWebView = null;
                }
                recreate();
                return true;
            }
        });

        // Set WebChromeClient for Receipt File Chooser (Camera & Gallery picker)
        mWebView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                super.onProgressChanged(view, newProgress);
                if (newProgress >= 100) {
                    mSwipeRefresh.setRefreshing(false);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback,
                                              FileChooserParams fileChooserParams) {
                // Cancel any pending callbacks
                if (mFilePathCallback != null) {
                    mFilePathCallback.onReceiveValue(null);
                    mFilePathCallback = null;
                }
                mFilePathCallback = filePathCallback;

                Intent takePictureIntent = null;
                File photoFile = null;
                try {
                    photoFile = createImageFile();
                    mCameraPhotoPath = photoFile.getAbsolutePath();
                    Uri photoURI = FileProvider.getUriForFile(MainActivity.this,
                            getApplicationContext().getPackageName() + ".fileprovider",
                            photoFile);
                    mCameraPhotoUri = photoURI;

                    takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoURI);
                    takePictureIntent.setClipData(ClipData.newRawUri("Receipt Photo", photoURI));
                    takePictureIntent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                } catch (Exception ex) {
                    mCameraPhotoPath = null;
                    mCameraPhotoUri = null;
                }

                // Gallery picker intent
                Intent contentSelectionIntent = fileChooserParams.createIntent();
                contentSelectionIntent.setType("image/*");

                Intent[] intentArray;
                if (takePictureIntent != null) {
                    intentArray = new Intent[]{takePictureIntent};
                } else {
                    intentArray = new Intent[0];
                }

                Intent chooserIntent = new Intent(Intent.ACTION_CHOOSER);
                chooserIntent.putExtra(Intent.EXTRA_INTENT, contentSelectionIntent);
                chooserIntent.putExtra(Intent.EXTRA_TITLE, "Select Receipt Photo");
                chooserIntent.putExtra(Intent.EXTRA_INITIAL_INTENTS, intentArray);

                try {
                    mFileChooserLauncher.launch(chooserIntent);
                } catch (ActivityNotFoundException e) {
                    mFilePathCallback = null;
                    Toast.makeText(MainActivity.this, "Cannot open photo chooser", Toast.LENGTH_SHORT).show();
                    return false;
                }

                return true;
            }
        });
    }

    private void handleDownload(String url, String userAgent, String contentDisposition, String mimeType) {
        try {
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            if (mimeType != null && !mimeType.isEmpty()) {
                request.setMimeType(mimeType);
            }
            String cookies = CookieManager.getInstance().getCookie(url);
            if (cookies != null && !cookies.isEmpty()) {
                request.addRequestHeader("cookie", cookies);
            }
            if (userAgent != null && !userAgent.isEmpty()) {
                request.addRequestHeader("User-Agent", userAgent);
            }
            request.setDescription("Downloading Wang transactions data...");
            String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
            if (filename == null || filename.isEmpty() || filename.endsWith(".bin")) {
                filename = "wang_transactions.csv";
            }
            request.setTitle(filename);
            request.allowScanningByMediaScanner();
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);

            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            if (dm != null) {
                dm.enqueue(request);
                Toast.makeText(getApplicationContext(), "Downloading " + filename + " to Downloads...", Toast.LENGTH_SHORT).show();
            }
        } catch (Exception e) {
            try {
                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                startActivity(intent);
            } catch (Exception ex) {
                Toast.makeText(getApplicationContext(), "Unable to download file", Toast.LENGTH_SHORT).show();
            }
        }
    }

    private void injectScrollHandler(WebView view) {
        String script = "(function() {" +
                "  if (window.__wangTouchBridgeInstalled) return;" +
                "  window.__wangTouchBridgeInstalled = true;" +
                "  function isScrollable(el) {" +
                "    if (!el || el === document.body || el === document.documentElement) return false;" +
                "    if (el.classList && (" +
                "      el.classList.contains('sheet-scroll') ||" +
                "      el.classList.contains('cat-grid') ||" +
                "      el.classList.contains('cat-cell') ||" +
                "      el.classList.contains('picker-list') ||" +
                "      el.classList.contains('picker-icon-grid') ||" +
                "      el.classList.contains('filter-sheet-body') ||" +
                "      el.classList.contains('filter-cats-wrap') ||" +
                "      el.classList.contains('sheet')" +
                "    )) return true;" +
                "    try {" +
                "      var s = window.getComputedStyle(el);" +
                "      var oy = s.overflowY; var ox = s.overflowX;" +
                "      return ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight + 2) ||" +
                "             ((ox === 'auto' || ox === 'scroll') && el.scrollWidth > el.clientWidth + 2);" +
                "    } catch(e) { return false; }" +
                "  }" +
                "  function findScrollable(target) {" +
                "    var el = target;" +
                "    while (el && el !== document.body && el !== document.documentElement) {" +
                "      if (isScrollable(el)) return el;" +
                "      el = el.parentElement;" +
                "    }" +
                "    return null;" +
                "  }" +
                "  function hasActiveSheetOrOverlay() {" +
                "    var openSheet = document.querySelector('.sheet.open, .detail-sheet.open, .budget-sheet.open, .filter-sheet.open, .confirm-sheet.open, .picker.open, .date-sheet.open, .month-popover.open, .modal-open, #lightbox.active');" +
                "    if (openSheet) return true;" +
                "    var overlay = document.querySelector('.sheet-overlay.show, .detail-overlay.show, .picker-overlay.show, .date-overlay.show, .filter-overlay.show, .confirm-overlay.show, .budget-overlay.show');" +
                "    if (overlay) return true;" +
                "    var a = document.activeElement;" +
                "    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT')) return true;" +
                "    return false;" +
                "  }" +
                "  function syncState(touchTarget) {" +
                "    if (!window.AndroidBridge) return;" +
                "    var path = window.location.pathname;" +
                "    var isForm = path.includes('/new') || path.includes('/edit') || path.includes('/delete') ||" +
                "                 path.includes('/login') || path.includes('/signup');" +
                "    if (isForm) {" +
                "      window.AndroidBridge.setPullToRefreshEnabled(false);" +
                "      window.AndroidBridge.setScrollableActive(true);" +
                "      return;" +
                "    }" +
                "    var isScroll = touchTarget ? !!findScrollable(touchTarget) : false;" +
                "    var overlay = hasActiveSheetOrOverlay();" +
                "    window.AndroidBridge.setScrollableActive(isScroll || overlay);" +
                "  }" +
                "  document.addEventListener('touchstart', function(e) { syncState(e.target); }, { passive: true, capture: true });" +
                "  document.addEventListener('touchmove', function(e) {" +
                "    if (findScrollable(e.target) && window.AndroidBridge) window.AndroidBridge.setScrollableActive(true);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('touchend', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 60);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('touchcancel', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 60);" +
                "  }, { passive: true, capture: true });" +
                "  document.addEventListener('focusin', function(e) {" +
                "    if (window.AndroidBridge) window.AndroidBridge.setScrollableActive(true);" +
                "  }, { capture: true });" +
                "  document.addEventListener('focusout', function(e) {" +
                "    setTimeout(function() { syncState(null); }, 150);" +
                "  }, { capture: true });" +
                "  window.addEventListener('popstate', function() { syncState(null); });" +
                "  document.addEventListener('turbo:load', function() { syncState(null); });" +
                "  document.addEventListener('turbo:render', function() { syncState(null); });" +
                "  syncState(null);" +
                "})();";
        view.evaluateJavascript(script, null);
    }

    private File createImageFile() throws IOException {
        String timeStamp = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(new Date());
        String imageFileName = "JPEG_" + timeStamp + "_";
        File storageDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES);
        if (storageDir == null || !storageDir.exists()) {
            storageDir = getCacheDir();
        }
        return File.createTempFile(
                imageFileName,  /* prefix */
                ".jpg",         /* suffix */
                storageDir      /* directory */
        );
    }

    private void setupFileChooserLauncher() {
        mFileChooserLauncher = registerForActivityResult(
                new ActivityResultContracts.StartActivityForResult(),
                new ActivityResultCallback<ActivityResult>() {
                    @Override
                    public void onActivityResult(ActivityResult result) {
                        Uri[] results = null;

                        // Check if response is positive
                        if (result.getResultCode() == RESULT_OK) {
                            Intent intent = result.getData();

                            // 1. Check if camera capture succeeded and produced a valid photo file
                            boolean isCamera = false;
                            if (mCameraPhotoPath != null) {
                                File file = new File(mCameraPhotoPath);
                                if (file.exists() && file.length() > 0) {
                                    isCamera = true;
                                }
                            }

                            // If camera produced the photo and intent has no specific gallery data
                            if (isCamera && (intent == null || (intent.getData() == null && intent.getClipData() == null))) {
                                if (mCameraPhotoUri != null) {
                                    results = new Uri[]{mCameraPhotoUri};
                                } else if (mCameraPhotoPath != null) {
                                    try {
                                        Uri uri = FileProvider.getUriForFile(MainActivity.this,
                                                getApplicationContext().getPackageName() + ".fileprovider",
                                                new File(mCameraPhotoPath));
                                        results = new Uri[]{uri};
                                    } catch (Exception e) {
                                        results = new Uri[]{Uri.fromFile(new File(mCameraPhotoPath))};
                                    }
                                }

                                // If callback was lost due to activity recreation under memory pressure
                                if (mFilePathCallback == null && mCameraPhotoPath != null) {
                                    mPendingCapturedPhotoBase64 = readImageAsBase64DataUrl(mCameraPhotoPath);
                                    deliverPendingPhotoToWebView();
                                }
                            } else if (intent != null) {
                                // 2. Gallery / Document / File picker selection
                                if (intent.getClipData() != null) {
                                    int count = intent.getClipData().getItemCount();
                                    results = new Uri[count];
                                    for (int i = 0; i < count; i++) {
                                        results[i] = intent.getClipData().getItemAt(i).getUri();
                                    }
                                } else if (intent.getData() != null) {
                                    results = new Uri[]{intent.getData()};
                                } else if (isCamera && mCameraPhotoUri != null) {
                                    results = new Uri[]{mCameraPhotoUri};
                                }
                            } else if (isCamera && mCameraPhotoUri != null) {
                                results = new Uri[]{mCameraPhotoUri};
                                if (mFilePathCallback == null && mCameraPhotoPath != null) {
                                    mPendingCapturedPhotoBase64 = readImageAsBase64DataUrl(mCameraPhotoPath);
                                    deliverPendingPhotoToWebView();
                                }
                            }
                        }

                        // Cleanup empty temp file if camera was cancelled without capture
                        if (results == null && mCameraPhotoPath != null) {
                            try {
                                File file = new File(mCameraPhotoPath);
                                if (file.exists() && file.length() == 0) {
                                    file.delete();
                                }
                            } catch (Exception ignored) {}
                        }

                        if (mFilePathCallback != null) {
                            mFilePathCallback.onReceiveValue(results);
                            mFilePathCallback = null;
                        }
                    }
                }
        );
    }

    private String readImageAsBase64DataUrl(String filePath) {
        try {
            File file = new File(filePath);
            if (!file.exists() || file.length() == 0) return null;

            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inJustDecodeBounds = true;
            BitmapFactory.decodeFile(filePath, options);

            int maxDim = 1280;
            int inSampleSize = 1;
            int width = options.outWidth;
            int height = options.outHeight;
            while ((width / inSampleSize) > maxDim || (height / inSampleSize) > maxDim) {
                inSampleSize *= 2;
            }

            options.inJustDecodeBounds = false;
            options.inSampleSize = inSampleSize;
            Bitmap bitmap = BitmapFactory.decodeFile(filePath, options);
            if (bitmap == null) return null;

            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            bitmap.compress(Bitmap.CompressFormat.JPEG, 85, baos);
            byte[] bytes = baos.toByteArray();
            bitmap.recycle();

            String base64 = Base64.encodeToString(bytes, Base64.NO_WRAP);
            return "data:image/jpeg;base64," + base64;
        } catch (Exception e) {
            return null;
        }
    }

    private void deliverPendingPhotoToWebView() {
        if (mWebView != null && mPendingCapturedPhotoBase64 != null) {
            String js = "if (window.wangAttachCapturedPhoto) { window.wangAttachCapturedPhoto('" + mPendingCapturedPhotoBase64 + "'); }";
            mWebView.evaluateJavascript(js, val -> {
                if (val != null && "true".equalsIgnoreCase(val.trim().replace("\"", ""))) {
                    mPendingCapturedPhotoBase64 = null;
                }
            });
        }
    }

    private void setupBackNavigation() {
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (mWebView != null && mWebView.canGoBack()) {
                    mWebView.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        if (mWebView != null) {
            mWebView.saveState(outState);
        }
        if (mCameraPhotoPath != null) {
            outState.putString("camera_photo_path", mCameraPhotoPath);
        }
        if (mCameraPhotoUri != null) {
            outState.putParcelable("camera_photo_uri", mCameraPhotoUri);
        }
        if (mPendingCapturedPhotoBase64 != null) {
            outState.putString("pending_photo_base64", mPendingCapturedPhotoBase64);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (mWebView != null) {
            mWebView.onPause();
        }
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (mWebView != null) {
            mWebView.onResume();
            // If the WebView was killed, cleared or lost while in background, reload immediately
            if (mWebView.getUrl() == null) {
                mWebView.loadUrl(getString(R.string.app_web_url));
            }
        }
        if (mSwipeRefresh != null) {
            mSwipeRefresh.setRefreshing(false);
        }
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onDestroy() {
        if (mWebView != null) {
            mWebView.destroy();
        }
        super.onDestroy();
    }
}
