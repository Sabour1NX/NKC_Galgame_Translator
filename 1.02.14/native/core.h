// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>
#ifdef NKC_GALGAME_TRANSLATOR_EXPORTS
#define GL_API extern "C" __declspec(dllexport)
#else
#define GL_API extern "C" __declspec(dllimport)
#endif

struct GLRegion {
    int32_t x, y, width, height;
    uint32_t background; // Win32 COLORREF: 0x00bbggrr
    uint32_t foreground;
    int32_t font_size;
    int32_t final; // 0: mask only currently rendered wrapped lines; 1: full original rectangle.
    const wchar_t* text;
    uint64_t track_id; // Stable text-object identity; zero is an index-scoped diagnostic object.
    uint64_t revision; // New source text revision resets accumulated font fitting.
};

// Source physical-row rectangles and ink bounds, relative to the GLRegion.
struct GLSourceRow {
    int32_t x, y, width, height;
    int32_t ink_x, ink_y, ink_width, ink_height;
    int32_t font_size;
};

GL_API uint32_t gl_abi_version(); // GLRegion layout ABI, currently 2.
GL_API uint64_t gl_video_memory_mb(uint32_t vendor); // Vendor 0 accepts any hardware adapter.
GL_API void* gl_create();
GL_API void gl_destroy(void* context);
// JSON UTF-8 strings are borrowed and valid until the next call on this thread.
GL_API const char* gl_languages();
GL_API const char* gl_capture_ocr(void* context, int x, int y, int width, int height, const wchar_t* language);
GL_API const char* gl_capture_frame(void* context, int x, int y, int width, int height);
GL_API int gl_copy_frame(void* context, uint8_t* destination, int capacity);
// Recognize caller-owned tightly packed BGRA bytes without capturing or changing
// the capture hash. 1..4096 per dimension, length exactly width*height*4. Results
// use image-relative coordinates. Call on an MTA worker; pointers remain valid
// until this synchronous call returns. GLRegion layout remains ABI 2.
GL_API const char* gl_ocr_bgra(const uint8_t* pixels, int length, int width, int height, const wchar_t* language);
GL_API void gl_reset(void* context);
// Context-local GDI font family, 1..31 UTF-16 units, well-formed Unicode,
// no C0/C1 controls or whitespace-only name. Caller supplies valid NUL-terminated
// input. 1 accepts, 0 rejects without changing the font; gl_error gives fixed text.
// New names asynchronously repaint pending regions and reset font fitting;
// same name is a no-op. Missing installed names use Windows GDI font fallback.
GL_API int gl_set_font(void* context, const wchar_t* family);
// Additive ABI 2. Booleans 0/1; pixel sizes 8..512, minimum<=maximum.
// Manual font never shrinks. Overflow preserves the source. Screenshot inclusion
// uses HWND-only WGC for OCR; unbound diagnostic overlays stay capture-excluded.
GL_API int gl_overlay_options(void* context,int automatic,int size,int minimum,int maximum,int screenshots);
// At most 512 regions, 64000 UTF-16 units per text and 1048576 per batch;
// font_size 0..512. Caller supplies valid pointers and NUL-terminated strings.
// Validation failure returns 0 without submitting a partial overlay snapshot.
GL_API int gl_overlay(void* context, const GLRegion* regions, int count);
// Additive API; GLRegion ABI remains 2. offsets has count+1 monotonic entries,
// starts at zero and ends at row_count. 0 rows opts a region into legacy layout,
// otherwise 1..32 contained, non-overlapping source rows are required.
// Fixed rows copy the most recent captured background opaquely and repair only
// foreground-consistent glyph/antialias pixels. Non-mask RGB is unchanged.
// Source ink and COLORREF foreground guide the mask; contradictory/dense or
// boundary-crossing evidence suppresses translated text and preserves source.
// There is no whole-row blur/interpolation. Hidden texture is only approximated.
// No pixels outside the captured frame are read. With an existing frame, invalid
// bounds/budget/allocation hide the overlay if an exact source copy is unavailable.
// Without a capture, legacy diagnostic rendering uses the solid region color.
// Textures have a 64MiB snapshot budget; each repair uses <=1M patch pixels and
// <=512K source-ink pixels. Cache keys include foreground color and source rows.
// Additive diagnostics: aero, background_opaque, background_frame, builds,
// background_suppressed, background_mask_pixels, background_repaired_pixels,
// background_reason. Suppression never paints translation over source text.
GL_API int gl_overlay_fixed(void* context, const GLRegion* regions, int count,
    const GLSourceRow* rows, int row_count, const int32_t* offsets);
// origins contains 2*count capture-origin int32 coordinates. Anchored objects
// follow same-size client moves at 16ms timer cadence without OCR/API requests.
// Resize, focus loss and out-of-client placement hide until fresh submission.
GL_API int gl_overlay_anchored(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int row_count,const int32_t* offsets,const int32_t* origins);
// ABI 2 additive: count parallel NUL-terminated family names (1..31 UTF-16
// units) and pixel flags (0/1). origins may be null for diagnostic placement.
GL_API int gl_overlay_styled(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int row_count,const int32_t* offsets,const int32_t* origins,
    const wchar_t* const* families,const int32_t* pixel_fonts);
// Additive ABI 2. center_labels contains count flags. Bit 0 centers a single
// source row. Bit 1 means the source glyphs are temporarily faded, according
// to a bounded pixel check. Bit 2 retains the prior background until replacement.
// Ink still describes the original glyphs.
GL_API int gl_overlay_labels(void* context,const GLRegion* regions,int count,
    const GLSourceRow* rows,int row_count,const int32_t* offsets,const int32_t* origins,
    const wchar_t* const* families,const int32_t* pixel_fonts,const int32_t* center_labels);
// True only for the installed requested face and all supplied BMP glyphs.
// <=4096 UTF-16 units; supplementary-plane text returns false conservatively.
GL_API int gl_font_supports(const wchar_t* family,const wchar_t* text);
// Read-only JSON of the last completed render; does not capture screen contents.
// The compositor stages RGB + opaque coverage alpha before an atomic layered
// commit (including size/position); it never shows an uninitialized first frame.
// Additional paint diagnostics: atomic_layered, first_show_commits, failures.
// Paint/upload failure hides the overlay and leaves the original source visible.
GL_API const char* gl_overlay_snapshot(void* context);
GL_API void gl_hide(void* context);
GL_API void gl_set_target(void* context, uintptr_t window, uint32_t process_id);
GL_API const char* gl_error();
