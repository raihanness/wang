package dev.raihan.wang;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
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
        String customUA = webSettings.getUserAgentString() + " WangNativeAndroid/1.0.4";
        webSettings.setUserAgentString(customUA);

        // Persistent Cookies & Session management
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(mWebView, true);

        // Enable fast scroll physics and disable overscroll glow
        mWebView.setOverScrollMode(View.OVER_SCROLL_NEVER);

        // Register AndroidBridge JavaScript interface
        mWebView.addJavascriptInterface(new WebAppInterface(), "AndroidBridge");

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

                    takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoURI);
                    takePictureIntent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                } catch (Exception ex) {
                    mCameraPhotoPath = null;
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
                        if (mFilePathCallback == null) return;

                        Uri[] results = null;

                        // Check if response is positive
                        if (result.getResultCode() == RESULT_OK) {
                            Intent intent = result.getData();

                            // Check for Camera Capture result
                            if (intent == null || intent.getData() == null && intent.getClipData() == null) {
                                if (mCameraPhotoPath != null) {
                                    results = new Uri[]{Uri.fromFile(new File(mCameraPhotoPath))};
                                }
                            } else {
                                // Gallery / Document selection
                                if (intent.getClipData() != null) {
                                    int count = intent.getClipData().getItemCount();
                                    results = new Uri[count];
                                    for (int i = 0; i < count; i++) {
                                        results[i] = intent.getClipData().getItemAt(i).getUri();
                                    }
                                } else if (intent.getData() != null) {
                                    results = new Uri[]{intent.getData()};
                                }
                            }
                        }

                        mFilePathCallback.onReceiveValue(results);
                        mFilePathCallback = null;
                    }
                }
        );
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
