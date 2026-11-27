// SPDX-License-Identifier: MIT
// Included after the legacy compositor types. Fixed rows never grow an OCR box.
static bool fixedCombining(uint32_t scalar) {
    if ((scalar>=0xfe00 && scalar<=0xfe0f) || (scalar>=0xe0100 && scalar<=0xe01ef)
        || (scalar>=0x1f3fb && scalar<=0x1f3ff)) return true;
    if (scalar>0xffff) return false;
    wchar_t value=wchar_t(scalar); WORD kind=0;
    return GetStringTypeW(CT_CTYPE3,&value,1,&kind) && (kind&(C3_NONSPACING|C3_DIACRITIC|C3_VOWELMARK));
}
static uint32_t fixedScalar(std::wstring const& text,size_t& pos) {
    uint32_t value=text[pos++];
    if (highSurrogate(wchar_t(value)) && pos<text.size() && lowSurrogate(text[pos]))
        value=0x10000+((value-0xd800)<<10)+(text[pos++]-0xdc00);
    return value;
}
static std::vector<size_t> fixedClusters(std::wstring const& text) {
    std::vector<size_t> ends; size_t pos=0; bool join=false;
    uint32_t prior=0; int regionalRun=0;
    while (pos<text.size()) {
        auto value=fixedScalar(text,pos);
        bool regional=value>=0x1f1e6 && value<=0x1f1ff;
        bool attach=!ends.empty() && (join || value==0x200d || fixedCombining(value)
            || (regional && prior>=0x1f1e6 && prior<=0x1f1ff && regionalRun%2));
        if (attach) ends.back()=pos; else ends.push_back(pos);
        join=value==0x200d; regionalRun=regional ? regionalRun+1 : 0; prior=value;
    }
    return ends;
}
struct FixedInk { int top=0,height=0,left=0,right=0; bool measured=false; };
static FixedInk fixedInk(HDC dc,std::wstring const& text) {
    TEXTMETRICW metrics{}; GetTextMetricsW(dc,&metrics);
    FixedInk ink; int low=INT_MAX,high=INT_MIN; MAT2 transform{};
    transform.eM11.value=transform.eM22.value=1;
    // Bounded representative glyph sampling. Full shaping/advances are still
    // measured separately; unknown fallback glyphs use font cell metrics.
    for (size_t i=0;i<text.size() && i<128;++i) {
        auto ch=text[i]; if (ch<=L' ' || highSurrogate(ch) || lowSurrogate(ch)) continue;
        GLYPHMETRICS glyph{};
        if (GetGlyphOutlineW(dc,ch,GGO_METRICS,&glyph,0,nullptr,&transform)==GDI_ERROR || !glyph.gmBlackBoxY) continue;
        int top=metrics.tmAscent-glyph.gmptGlyphOrigin.y;
        low=std::min(low,top); high=std::max(high,top+int(glyph.gmBlackBoxY));
        ink.measured=true;
    }
    ink.top=ink.measured ? low : 0;
    ink.height=ink.measured ? high-low : metrics.tmHeight;
    return ink;
}
static std::wstring fixedFlatten(std::wstring text) {
    text.erase(std::remove(text.begin(),text.end(),L'\r'),text.end());
    for (size_t i=0;i<text.size();++i) if (text[i]==L'\n') {
        bool latin=i>0 && i+1<text.size() && latinWord(text[i-1]) && latinWord(text[i+1]);
        text[i]=latin ? L' ' : wchar_t(0x200b);
    }
    text.erase(std::remove(text.begin(),text.end(),wchar_t(0x200b)),text.end());
    return text;
}
struct FixedRowQuality { int ink=0; std::vector<bool> uncertain; };
static FixedRowQuality fixedRowQuality(Region const& region) {
    FixedRowQuality quality; std::vector<int> heights;
    for(auto const& row:region.sourceRows) heights.push_back(row.ink_height);
    std::sort(heights.begin(),heights.end());
    quality.ink=heights.empty()?8:heights[heights.size()/2];
    quality.uncertain.assign(heights.size(),false);
    // Require multiple normal prose rows before treating a tiny OCR fragment
    // as weak font evidence. Menus, explicit font caps and short labels alone
    // are never a reason to discard a row or enlarge its original rectangle.
    size_t reliable=0;
    for(auto const& row:region.sourceRows)
        reliable+=row.ink_width>=8*quality.ink && row.ink_height*10>=quality.ink*7;
    if(heights.size()>=3 && reliable>=2 && reliable*2>=heights.size())
        for(size_t i=0;i<heights.size();++i) {
            auto const& row=region.sourceRows[i];
            quality.uncertain[i]=row.font_size==0 &&
                (row.ink_width<3*quality.ink || row.ink_height*10<quality.ink*7);
        }
    return quality;
}
static int fixedWidth(HDC dc,std::wstring const& text) {
    SIZE extent{};
    return GetTextExtentPoint32W(dc,text.data(),int(text.size()),&extent)?extent.cx:INT_MAX;
}
static void fixedBalanceContinuation(HDC dc,Region const& region,std::vector<std::wstring>& pieces) {
    auto quality=fixedRowQuality(region);
    for(size_t i=1;i<pieces.size();++i) {
        auto const& row=region.sourceRows[i]; auto const& previous=region.sourceRows[i-1];
        int gap=row.ink_y-previous.ink_y-previous.ink_height;
        if(!quality.uncertain[i] || row.ink_width>=3*quality.ink ||
            previous.ink_width<8*quality.ink || pieces[i-1].empty() ||
            gap<0 || gap>quality.ink || std::abs(row.ink_x-previous.ink_x)>std::max(3,quality.ink/2) ||
            fixedWidth(dc,pieces[i])<=row.ink_width) continue;
        auto clusters=fixedClusters(pieces[i]);
        // A short physical continuation (e.g. a final punctuation row) must
        // not force every paragraph row to 14 px. Move only whole clusters
        // into the immediately preceding row's measured spare capacity.
        // Keep at least one cluster in the continuation; never grow any box.
        for(size_t n=0;n+1<clusters.size() && n<64;++n) {
            auto before=fixedFlatten(pieces[i-1]+L"\n"+pieces[i].substr(0,clusters[n]));
            if(fixedWidth(dc,before)>previous.ink_width) break;
            auto after=pieces[i].substr(clusters[n]);
            if(fixedWidth(dc,after)<=row.ink_width) {
                pieces[i-1]=std::move(before);pieces[i]=std::move(after);break;
            }
        }
    }
}
static std::vector<std::wstring> fixedPartition(HDC dc,Region const& region) {
    size_t rows=region.sourceRows.size();
    std::wstring input=region.text;
    input.erase(std::remove(input.begin(),input.end(),L'\r'),input.end());
    std::vector<std::wstring> result(rows);
    if (region.centerLabel) return {fixedFlatten(input)};
    if (region.final && size_t(std::count(input.begin(),input.end(),L'\n'))+1==rows) {
        size_t at=0;
        for (size_t i=0;i<rows;++i) {
            size_t end=input.find(L'\n',at); if (end==std::wstring::npos) end=input.size();
            result[i]=input.substr(at,end-at); at=end+1;
        }
        fixedBalanceContinuation(dc,region,result);
        return result;
    }
    auto text=fixedFlatten(input); auto ends=fixedClusters(text);
    if (text.empty()) return result;
    std::vector<int> cumulative(text.size()); SIZE extent{};
    if (!GetTextExtentExPointW(dc,text.data(),int(text.size()),INT_MAX,nullptr,cumulative.data(),&extent))
        return {text};
    size_t used=0; int remainingWidth=0;
    for (auto const& row:region.sourceRows) remainingWidth+=row.ink_width;
    for (size_t row=0;row<rows && used<ends.size();++row) {
        size_t begin=used ? ends[used-1] : 0;
        int before=begin ? cumulative[begin-1] : 0;
        int target=region.sourceRows[row].ink_width;
        if(!region.final) {
            // Keep the chosen source-relative font stable while streaming.
            // Only the prefix that fits available physical rows is painted;
            // the complete cumulative text stays in Region until final fit.
            size_t finish=used;
            while(finish<ends.size() && cumulative[ends[finish]-1]-before<=target) ++finish;
            if(finish==used) continue;
            size_t end=ends[finish-1]; result[row]=text.substr(begin,end-begin);used=finish;
            continue;
        }
        if (region.final) target=std::max(1,int(std::llround(double(extent.cx-before)*target/remainingWidth)));
        size_t finish=used;
        while (finish+1<ends.size() && cumulative[ends[finish]-1]-before<target) ++finish;
        if (finish>used && cumulative[ends[finish]-1]-before>target) --finish;
        if (row+1==rows) finish=ends.size()-1;
        else if (region.final && ends.size()-used>=rows-row)
            finish=std::min(finish,ends.size()-(rows-row));
        size_t end=ends[finish];
        // Prefer a word boundary near the allocated width; never split a
        // cluster, and never consume a future physical source row.
        if (row+1<rows && end<text.size() && latinWord(text[end-1]) && latinWord(text[end])) {
            size_t candidate=finish;
            while (candidate>used && latinWord(text[ends[candidate-1]-1])) --candidate;
            if (candidate>used) { finish=candidate-1; end=ends[finish]; }
        }
        result[row]=text.substr(begin,end-begin); used=finish+1;
        remainingWidth-=region.sourceRows[row].ink_width;
    }
    return result;
}
static bool fixedLines(HDC dc,Region const& region,std::vector<RenderLine>& lines) {
    auto pieces=fixedPartition(dc,region); if (pieces.size()!=region.sourceRows.size()) return false;
    auto quality=fixedRowQuality(region);
    bool fits=true; size_t offset=0;
    for (size_t i=0;i<pieces.size();++i) {
        auto const& row=region.sourceRows[i]; auto text=std::move(pieces[i]);
        while (!text.empty() && (text.back()==L' ' || text.back()==L'\t')) text.pop_back();
        while (!text.empty() && (text.front()==L' ' || text.front()==L'\t')) text.erase(text.begin());
        RenderLine line{text,row.ink_y,0,row.ink_height,offset,text.size()};
        line.x=row.ink_x;
        line.clip={row.x,row.y,row.x+row.width,row.y+row.height};
        if (!text.empty()) {
            if (text.size()>8192) { fits=false; lines.push_back(std::move(line)); continue; }
            auto ink=fixedInk(dc,text); line.y=row.ink_y-ink.top;
            line.inkHeight=ink.height; line.inkTop=row.ink_y;
            std::vector<int> cumulative(text.size()); SIZE extent{};
            if (!GetTextExtentExPointW(dc,text.data(),int(text.size()),INT_MAX,nullptr,cumulative.data(),&extent)) return false;
            line.width=extent.cx;
            int available=region.centerLabel ? row.width-4 : row.ink_width;
            if (region.centerLabel) line.x=row.x+(row.width-extent.cx)/2;
            bool rowFits=extent.cx<=available && ink.height<=row.ink_height;
            line.drawable=rowFits;
            fits=fits && (rowFits || quality.uncertain[i]);
            line.advances.resize(text.size()); int prior=0;
            for (size_t j=0;j<text.size();++j) { line.advances[j]=cumulative[j]-prior; prior=cumulative[j]; }
            auto clusters=fixedClusters(text);
            if (!region.centerLabel && region.final && clusters.size()>1 && extent.cx<=row.ink_width) {
                int extra=row.ink_width-extent.cx,assigned=0;
                for (size_t j=0;j+1<clusters.size();++j) {
                    int total=int((int64_t(extra)*(j+1))/(clusters.size()-1));
                    line.advances[clusters[j]-1]+=total-assigned; assigned=total;
                }
                line.width=row.ink_width;
            }
        }
        offset+=text.size(); lines.push_back(std::move(line));
    }
    return fits;
}
static HFONT fixedFont(int height,std::wstring const& family,bool pixel=false) {
    return CreateFontW(-height,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
        DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,pixel?NONANTIALIASED_QUALITY:CLEARTYPE_QUALITY,DEFAULT_PITCH,family.c_str());
}
static bool fixedGeometryContinues(std::vector<GLSourceRow> const& before,std::vector<GLSourceRow> const& after) {
    if(before.size()!=after.size()) return false;
    for(size_t i=0;i<before.size();++i) {
        auto const& a=before[i]; auto const& b=after[i];
        if(a.font_size!=b.font_size ||
            std::abs(a.ink_width-b.ink_width)>std::max(2,a.ink_width/5) ||
            std::abs(a.ink_height-b.ink_height)>std::max(2,a.ink_height/5)) return false;
    }
    return true;
}
static void prepareFixedOverlay(OverlayWindow& item,bool continuing,std::wstring const& family,OverlayOptions const& options,
                                bool independent=true) {
    item.maskReady=false;
    HDC dc=GetDC(item.hwnd); if (!dc) return;
    auto quality=fixedRowQuality(item.region);
    int sourceInk=quality.ink;
    int ceiling=std::clamp(sourceInk,8,512);
    // A fixed representative alphabet anchors the em size. Calibrating from
    // the currently streamed prefix made punctuation or short/low glyphs grow
    // larger than the neighboring lines of the same source paragraph.
    HFONT probe=fixedFont(ceiling,family,item.region.pixelFont);
    if (probe) {
        auto prior=SelectObject(dc,probe);
        auto ink=fixedInk(dc,L"\u56fdAg");
        if (ink.height>0) ceiling=std::clamp(int(std::lround(double(ceiling)*sourceInk/ink.height)),8,512);
        SelectObject(dc,prior); DeleteObject(probe);
    }
    for (auto const& row:item.region.sourceRows)
        if (row.font_size>0) ceiling=std::min(ceiling,std::max(8,row.font_size));
    ceiling=options.automatic?std::clamp(ceiling,options.minimum,options.maximum):options.size;
    int minimum=options.automatic?options.minimum:options.size;
    int previous=item.independentFontPixels>0?item.independentFontPixels:item.fontPixels;
    if (options.automatic && continuing && previous>0) ceiling=std::min(ceiling,previous);
    HFONT accepted=nullptr; std::vector<RenderLine> chosen; int selected=minimum; bool fits=false;
    int low=minimum,high=ceiling;
    while (low<=high) {
        int size=(low+high)/2; HFONT font=fixedFont(size,family,item.region.pixelFont); if (!font) break;
        auto old=SelectObject(dc,font); std::vector<RenderLine> lines;
        bool current=fixedLines(dc,item.region,lines);
        SelectObject(dc,old);
        if (current) {
            if (accepted) DeleteObject(accepted);
            accepted=font; selected=size; chosen=std::move(lines); fits=true; low=size+1;
        } else { DeleteObject(font); high=size-1; }
    }
    if (!accepted) {
        accepted=fixedFont(minimum,family,item.region.pixelFont);
        if (accepted) { auto old=SelectObject(dc,accepted); fixedLines(dc,item.region,chosen); SelectObject(dc,old); }
    }
    if (accepted) {
        if (item.font) DeleteObject(item.font); item.font=accepted;
        item.fontPixels=selected; item.lines=std::move(chosen); item.fits=fits;
        if(independent) item.independentFontPixels=selected;
        auto old=SelectObject(dc,accepted); wchar_t face[LF_FACESIZE]{};
        GetTextFaceW(dc,LF_FACESIZE,face); item.fontFace=face; SelectObject(dc,old);
    } else { item.lines.clear(); item.fits=false; }
    ReleaseDC(item.hwnd,dc);
    HRGN mask=CreateRectRgn(0,0,0,0);
    if (item.region.coverSource) {
        for (auto const& row:item.region.sourceRows) {
            HRGN stripe=CreateRectRgn(row.x,row.y,row.x+row.width,row.y+row.height);
            CombineRgn(mask,mask,stripe,RGN_OR); DeleteObject(stripe);
        }
        item.stageMask(mask);
        return;
    }
    if (item.fits) for (size_t i=0;i<item.region.sourceRows.size();++i) {
        auto const& row=item.region.sourceRows[i]; auto const& line=item.lines[i];
        if(!line.drawable) continue;
        if (!item.region.final && line.text.empty()) continue;
        // Once translation begins on a physical row, cover all its original
        // glyphs. Rows waiting for their first translated glyph stay visible.
        int left=row.x, right=row.x+row.width;
        if (item.region.centerLabel) {
            int bleed=item.region.toolbarButton ? 2 : 1;
            left=std::max(row.x,std::min(row.ink_x-bleed,line.x-2));
            right=std::min(row.x+row.width,std::max(row.ink_x+row.ink_width+bleed,line.x+line.width+2));
        }
        HRGN stripe=CreateRectRgn(left,row.y,right,row.y+row.height);
        CombineRgn(mask,mask,stripe,RGN_OR); DeleteObject(stripe);
    }
    item.stageMask(mask);
}

static int fixedExplicitCap(Region const& region) {
    int cap=0;
    for (auto const& row:region.sourceRows)
        if (row.font_size>0) cap=cap?std::min(cap,row.font_size):row.font_size;
    return cap;
}
static bool fixedCloseColor(COLORREF first,COLORREF second,int tolerance) {
    return std::abs(int(GetRValue(first))-int(GetRValue(second)))<=tolerance &&
        std::abs(int(GetGValue(first))-int(GetGValue(second)))<=tolerance &&
        std::abs(int(GetBValue(first))-int(GetBValue(second)))<=tolerance;
}
static bool fixedParagraphNeighbors(OverlayWindow const& above,OverlayWindow const& below) {
    auto const& a=above.region; auto const& b=below.region;
    if (a.centerLabel || b.centerLabel || a.standaloneSubtitle || b.standaloneSubtitle ||
        a.sourceRows.empty() || b.sourceRows.empty() ||
        above.fontFace!=below.fontFace || a.fontFamily!=b.fontFamily || a.pixelFont!=b.pixelFont ||
        fixedExplicitCap(a)!=fixedExplicitCap(b) || (!(a.subtitle && b.subtitle) && !fixedCloseColor(a.bg,b.bg,20)) ||
        !fixedCloseColor(a.fg,b.fg,28)) return false;
    auto const& last=a.sourceRows.back(); auto const& first=b.sourceRows.front();
    int ah=last.ink_height,bh=first.ink_height,inkMinimum=std::min(ah,bh);
    if (inkMinimum<=0 || std::max(ah,bh)>inkMinimum*1.25) return false;
    int gap=b.y+first.ink_y-(a.y+last.ink_y+last.ink_height);
    int leftA=a.x+a.sourceRows.front().ink_x,leftB=b.x+first.ink_x;
    // Font grouping does not merge text/rectangles or bridge blank paragraphs.
    // Different source sizes, title styles, columns and explicit caps stay apart.
    const double maxGap=(a.subtitle && b.subtitle) ? .95 : .65;
    return gap>=0 && gap<=std::max(4,int(inkMinimum*maxGap)) &&
        std::abs(leftA-leftB)<=std::min(12,std::max(3,int(inkMinimum*.4)));
}
static bool fixedActionPeers(OverlayWindow const& first,OverlayWindow const& second) {
    auto const& a=first.region; auto const& b=second.region;
    if (a.menuButton && b.menuButton && first.fits && second.fits &&
        first.fontFace==second.fontFace && a.fontFamily==b.fontFamily && a.pixelFont==b.pixelFont &&
        a.x==b.x && a.w==b.w && a.h==b.h) return true;
    if (!a.centerLabel || !b.centerLabel || !first.fits || !second.fits ||
        first.fontFace!=second.fontFace || a.fontFamily!=b.fontFamily || a.pixelFont!=b.pixelFont ||
        !fixedCloseColor(a.bg,b.bg,20) || !fixedCloseColor(a.fg,b.fg,28)) return false;
    auto const& ra=a.sourceRows.front(); auto const& rb=b.sourceRows.front();
    int height=std::min(ra.ink_height,rb.ink_height);
    return std::abs(ra.ink_height-rb.ink_height)<=2 &&
        std::abs((int64_t(a.y)+ra.ink_y)-(int64_t(b.y)+rb.ink_y))<=2 &&
        std::abs(int64_t(a.x)-b.x)<=32*height &&
        std::abs(first.fontPixels-second.fontPixels)<=2;
}
static void harmonizeFixedFonts(std::vector<std::unique_ptr<OverlayWindow>>& windows,
                               std::wstring const& family,OverlayOptions const& options) {
    for (auto& item:windows) item->fontPeers=1;
    if (!options.automatic) return;
    std::vector<size_t> parent(windows.size());
    for (size_t i=0;i<parent.size();++i) parent[i]=i;
    auto root=[&parent](size_t value) { while(parent[value]!=value) value=parent[value]; return value; };
    for(size_t i=0;i<windows.size();++i) for(size_t j=i+1;j<windows.size();++j)
        if(fixedActionPeers(*windows[i],*windows[j]) ||
            fixedParagraphNeighbors(*windows[i],*windows[j]) || fixedParagraphNeighbors(*windows[j],*windows[i]))
            parent[root(j)]=root(i);
    std::map<size_t,std::vector<size_t>> groups;
    for(size_t i=0;i<windows.size();++i) groups[root(i)].push_back(i);
    for(auto const& entry:groups) {
        if(entry.second.size()<2) continue;
        bool prose=false; int chosen=512,reliableChosen=512;size_t reliable=0;
        for(auto index:entry.second) {
            auto const& item=*windows[index]; chosen=std::min(chosen,item.fontPixels);
            bool normal=false,tiny=true;
            for(auto const& row:item.region.sourceRows) {
                normal=normal || row.ink_width>=8*row.ink_height;
                tiny=tiny && row.ink_width<3*row.ink_height;
            }
            prose=prose || normal;
            if(normal) ++reliable;
            if(!tiny) reliableChosen=std::min(reliableChosen,item.fontPixels);
        }
        // Multiple normal text objects establish body size. A lone tiny
        // fragment must not reduce every neighboring paragraph line; it is
        // still fitted at the shared size and keeps original pixels if it
        // cannot fit. Never move text between independent translation objects.
        if(entry.second.size()>=3 && reliable>=2 && reliable*2>=entry.second.size()) chosen=reliableChosen;
        if((!prose && !windows[entry.second.front()]->region.centerLabel) || chosen<options.minimum) continue;
        auto shared=options; shared.automatic=false; shared.size=chosen;
        for(auto index:entry.second) {
            auto& item=*windows[index]; item.fontPeers=int(entry.second.size());
            if(item.fontPixels!=chosen)
                prepareFixedOverlay(item,false,item.region.fontFamily.empty()?family:item.region.fontFamily,shared,false);
        }
    }
}
