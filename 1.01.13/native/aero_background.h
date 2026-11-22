// SPDX-License-Identifier: MIT
// Opaque glyph-only repair. Non-glyph source pixels remain byte-identical.
#pragma once
struct BackgroundFrame {
    int x=0,y=0,w=0,h=0;
    uint64_t sequence=0;
    std::vector<uint8_t> pixels;
    RECT anchor{};
    bool anchored=false;
};
struct RepairedBackground {
    std::vector<uint8_t> pixels;
    size_t masked=0,repaired=0;
    bool suppressed=false;
    char const* reason="no_frame";
};
static bool sameSourceRows(std::vector<GLSourceRow> const& a,std::vector<GLSourceRow> const& b) {
    if (a.size()!=b.size()) return false;
    for(size_t i=0;i<a.size();++i) {
        auto const& x=a[i];auto const& y=b[i];
        if(x.x!=y.x||x.y!=y.y||x.width!=y.width||x.height!=y.height||
           x.ink_x!=y.ink_x||x.ink_y!=y.ink_y||x.ink_width!=y.ink_width||x.ink_height!=y.ink_height) return false;
    }
    return true;
}
static RepairedBackground reconstructBackground(BackgroundFrame const& frame,Region const& r) {
    RepairedBackground result;result.suppressed=true;result.reason="source_unavailable";
    if(r.sourceRows.empty()||r.w<=0||r.h<=0||size_t(r.w)*r.h>4096u*4096u) return result;
    if(int64_t(r.x)<frame.x||int64_t(r.y)<frame.y||int64_t(r.x)+r.w>int64_t(frame.x)+frame.w||
       int64_t(r.y)+r.h>int64_t(frame.y)+frame.h) return result;
    if(frame.pixels.size()!=size_t(frame.w)*frame.h*4) return result;
    size_t count=size_t(r.w)*r.h,inkArea=0;
    for(auto const& row:r.sourceRows)inkArea+=size_t(row.ink_width)*row.ink_height;
    if(count>1048576u||inkArea>524288u) {result.reason="repair_budget";return result;}
    result.suppressed=false;
    result.pixels.resize(count*4);
    for(int y=0;y<r.h;++y) {
        auto at=(size_t(int64_t(r.y)-frame.y+y)*frame.w+size_t(int64_t(r.x)-frame.x))*4;
        std::copy_n(frame.pixels.data()+at,size_t(r.w)*4,result.pixels.data()+size_t(y)*r.w*4);
    }
    for(size_t at=3;at<result.pixels.size();at+=4)result.pixels[at]=255;
    // A retained source copy is also the exact no-translation fallback.
    auto original=result.pixels;
    std::array<int,3> foreground{GetBValue(r.fg),GetGValue(r.fg),GetRValue(r.fg)};
    auto pixel=[&](int x,int y) {return original.data()+(size_t(y)*r.w+x)*4;};
    std::array<int,3> background{GetBValue(r.bg),GetGValue(r.bg),GetRValue(r.bg)};
    // The blue toolbar is nearly uniform across each row. Sample clear strips
    // on either side; sampling immediately above a letter propagates its faint
    // antialiasing halo into vertical streaks.
    if (r.toolbarButton && r.sourceRows.size()==1) {
        auto const& row=r.sourceRows.front();
        int left=row.ink_x-2, right=row.ink_x+row.ink_width+2;
        int top=row.ink_y-2, bottom=row.ink_y+row.ink_height+2;
        bool clean=left>=3 && right+3<=r.w && top>=1 && bottom<r.h;
        size_t marks=0;
        for (int x=left;clean && x<right;++x) {
            for (int y:{top-1,bottom}) for(int c=0;c<3;++c)
                if (std::abs(int(pixel(x,y)[c])-background[c])>26) clean=false;
            for (int y=row.ink_y;y<row.ink_y+row.ink_height;++y)
                if (int(pixel(x,y)[2])-background[2]>52) ++marks;
        }
        if(clean && marks>=std::max<size_t>(3,inkArea/30)) {
            for(int y=top;y<bottom;++y) {
                std::array<int,3> a{},b{};
                for(int c=0;c<3;++c) for(int i=0;i<3;++i) {
                    a[c]+=pixel(i,y)[c]; b[c]+=pixel(r.w-1-i,y)[c];
                }
                int span=3*(r.w-1);
                for(int x=left;x<right;++x) for(int c=0;c<3;++c)
                    result.pixels[(size_t(y)*r.w+x)*4+c]=uint8_t(((r.w-1-x)*a[c]+x*b[c]+span/2)/span);
            }
            result.masked=result.repaired=size_t(right-left)*(bottom-top);
            result.reason="toolbar_background";
            return result;
        }
    }
    // A verified title button has a repeating grid. Sample an untouched
    // column at the same grid phase, including the current hover tint.
    if (r.menuButton && r.sourceRows.size()==1) {
        auto const& row=r.sourceRows.front();
        int left=row.ink_x,right=left+row.ink_width,top=row.ink_y,bottom=top+row.ink_height;
        if (left>=5 && right+5<r.w && top>=2 && bottom+2<=r.h) {
            bool matched=true;
            std::vector<int> columns;
            for (int x=left;x<right && matched;++x) {
                int best=INT_MAX,column=-1;
                for (int u=1;u<r.w-1;++u) {
                    if (u>=left-2 && u<right+2) continue;
                    int score=0;
                    for (int yy:{top-2,bottom+1}) for(int dx=-1;dx<=1;++dx) {
                        auto a=pixel(x+dx,yy),b=pixel(u+dx,yy);
                        for(int c=0;c<3;++c) score+=std::abs(int(a[c])-b[c]);
                    }
                    if(score<best) {best=score;column=u;}
                    if(!score) break;
                }
                matched=best<=54;
                columns.push_back(column);
            }
            if(matched) {
                for(int x=left;x<right;++x) for(int y=top;y<bottom;++y) {
                    auto sample=pixel(columns[x-left],y),current=pixel(x,y);
                    if(int(current[2])<=sample[2]+2) continue;
                    std::copy_n(sample,3,result.pixels.data()+(size_t(y)*r.w+x)*4);
                    ++result.masked;
                }
                auto edge=pixel(1,r.h/2);
                if (int(edge[0])-int(edge[2])<20 || result.masked<std::max<size_t>(4,inkArea/50) ||
                    result.masked>inkArea*2/3) {
                    result.pixels=original;
                    result.suppressed=true;
                    result.reason="button_source_changed";
                    return result;
                }
                result.repaired=result.masked;
                result.reason="button_grid_repaired";
                return result;
            }
        }
    }
    int signal=0;
    for(int c=0;c<3;++c) {
        int contrast=foreground[c]-background[c];
        signal+=contrast*contrast;
    }
    // A locally verified flat text surface permits complete cleanup of faint
    // and blinking glyphs, even when there are no solid foreground seeds.
    bool plain=signal>=4096;
    for(auto const& row:r.sourceRows) {
        if(!plain)break;
        int margins=0, marks=0;
        int right=row.ink_x+row.ink_width,bottom=row.ink_y+row.ink_height;
        int left=std::max(row.x,row.ink_x-1),top=std::max(row.y,row.ink_y-1);
        for(int y=top;y<std::min(row.y+row.height,bottom+1)&&plain;++y)
            for(int x=left;x<std::min(row.x+row.width,right+1);++x) {
                auto p=pixel(x,y);
                bool margin=x<row.ink_x||x>=right||y<row.ink_y||y>=bottom;
                if(margin)++margins;
                int dot=0;
                if(!margin)for(int c=0;c<3;++c) dot+=(int(p[c])-background[c])*(foreground[c]-background[c]);
                double a=double(dot)/signal;
                if(a>.035)++marks;
                if(a<-.09||a>1.09) {plain=false;break;}
                for(int c=0;c<3;++c) if(std::abs(p[c]-(background[c]+a*(foreground[c]-background[c])))>9) {
                    plain=false;break;
                }
                if(!plain)break;
            }
        plain=plain&&margins>=8&&(marks>=3||r.flashHeld)&&
            marks<=row.ink_width*row.ink_height*7/10;
    }
    if(plain) {
        for(auto const& row:r.sourceRows)
            for(int y=row.ink_y;y<row.ink_y+row.ink_height;++y)
                for(int x=row.ink_x;x<row.ink_x+row.ink_width;++x) {
                    size_t offset=(size_t(y)*r.w+x)*4;
                    auto out=result.pixels.data()+offset;
                    if(out[0]==background[0]&&out[1]==background[1]&&out[2]==background[2])continue;
                    for(int c=0;c<3;++c)out[c]=uint8_t(background[c]);
                    ++result.masked;++result.repaired;
                }
        result.reason="flat_glyph_repaired";
        return result;
    }
    auto distance=[&](uint8_t const* p) {
        return std::max({std::abs(int(p[0])-foreground[0]),std::abs(int(p[1])-foreground[1]),std::abs(int(p[2])-foreground[2])});
    };
    auto sourceDistance=[&](int x,int y) {
        int64_t fx=int64_t(r.x)-frame.x+x,fy=int64_t(r.y)-frame.y+y;
        if(fx<0||fy<0||fx>=frame.w||fy>=frame.h)return 256;
        return distance(frame.pixels.data()+(size_t(fy)*frame.w+size_t(fx))*4);
    };
    auto reject=[&](char const* why) {
        result.suppressed=true;result.reason=why;result.pixels=original;result.repaired=0;
    };
    std::vector<uint8_t> core(count,0),mask(count,0);
    for(auto const& row:r.sourceRows) {
        size_t seeds=0;
        int x0=row.ink_x,y0=row.ink_y,x1=x0+row.ink_width,y1=y0+row.ink_height;
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x) {
            auto p=pixel(x,y);
            bool mint=p[1]>=150 && int(p[1])-p[2]>=52 && int(p[1])-p[0]>=12 && int(p[0])-p[2]>=18;
            int brightStroke = r.centerLabel ? 178 : 210;
            if(distance(p)<=40 || (r.subtitle && (std::min({p[0],p[1],p[2]})>=brightStroke || mint))) {
                core[size_t(y)*r.w+x]=1;++seeds;
            }
        }
        if(seeds<3) {reject("foreground_missing");return result;}
        if(seeds>size_t(row.ink_width)*row.ink_height*7/10) {reject("dense_foreground");return result;}
        // A foreground-colored shape continuing out of the OCR ink rectangle
        // may be artwork, not a letter. Do not erase it or draw over it.
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x)if(core[size_t(y)*r.w+x]) {
            if((x==x0&&sourceDistance(x-1,y)<=40)||(x==x1-1&&sourceDistance(x+1,y)<=40)||
               (y==y0&&sourceDistance(x,y-1)<=40)||(y==y1-1&&sourceDistance(x,y+1)<=40)) {
                reject("foreground_leaks_boundary");return result;
            }
        }
    }
    mask=core;
    // Include antialias pixels only with actual foreground/background mixing
    // evidence near a core glyph. Unconditional dilation would damage a ring
    // or frame immediately beside a letter, so it is deliberately not used.
    constexpr int directions[8][2]={{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1},{1,-1},{-1,1}};
    for(auto const& row:r.sourceRows) {
        if(r.subtitle) {
            // The isolated subtitle pass identifies both the main stroke and
            // white punctuation. Include their antialiased dark outlines.
            int radius=std::clamp((row.ink_height+5)/10,2,5);
            // Centered white action labels have a soft fringe over the control artwork.
            if (r.centerLabel) radius=std::clamp((row.ink_height+3)/5,3,6);
            for(int y=row.ink_y;y<row.ink_y+row.ink_height;++y)
                for(int x=row.ink_x;x<row.ink_x+row.ink_width;++x) {
                    if(!core[size_t(y)*r.w+x])continue;
                    for(int yy=std::max(row.y,y-radius);yy<std::min(row.y+row.height,y+radius+1);++yy) {
                        auto start=mask.begin()+size_t(yy)*r.w;
                        std::fill(start+std::max(row.x,x-radius),start+std::min(row.x+row.width,x+radius+1),1);
                    }
                }
            continue;
        }
        int x0=std::max(row.x,row.ink_x-1),y0=std::max(row.y,row.ink_y-1);
        int x1=std::min(row.x+row.width,row.ink_x+row.ink_width+1);
        int y1=std::min(row.y+row.height,row.ink_y+row.ink_height+1);
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x) {
            size_t at=size_t(y)*r.w+x;if(core[at])continue;
            bool nearGlyph=false;
            for(int dy=-2;dy<=2&&!nearGlyph;++dy)for(int dx=-2;dx<=2;++dx) {
                int xx=x+dx,yy=y+dy;
                if(xx>=x0&&xx<x1&&yy>=y0&&yy<y1&&core[size_t(yy)*r.w+xx]) {nearGlyph=true;break;}
            }
            if(!nearGlyph)continue;
            auto p=pixel(x,y);
            for(auto const& d:directions) {
                int xx=x+3*d[0],yy=y+3*d[1];
                if(xx<row.x||xx>=row.x+row.width||yy<row.y||yy>=row.y+row.height)continue;
                if(core[size_t(yy)*r.w+xx])continue;
                auto b=pixel(xx,yy);double dot=0,norm=0;
                int contrast=0;
                for(int c=0;c<3;++c) {
                    double v=foreground[c]-b[c];dot+=(int(p[c])-b[c])*v;norm+=v*v;
                    contrast=std::max(contrast,std::abs(int(p[c])-b[c]));
                }
                if(norm<2500||contrast<18)continue;
                double alpha=dot/norm;if(alpha<.08||alpha>.97)continue;
                double residual=0;
                for(int c=0;c<3;++c)residual=std::max(residual,std::abs(p[c]-(b[c]+alpha*(foreground[c]-b[c]))));
                if(residual<=10) {mask[at]=1;break;}
            }
        }
    }
    auto luma=[](uint8_t const* p) {return (29*int(p[0])+150*int(p[1])+77*int(p[2]))/256;};
    int foregroundLuma=(29*foreground[0]+150*foreground[1]+77*foreground[2])/256;
    bool repairedOutline=false;
    std::vector<uint8_t> filled;
    for(auto const& row:r.sourceRows) {
        if(r.subtitle)break;
        int radius=std::clamp(2+row.ink_height/8,3,6);
        int x0=std::max(row.x,row.ink_x-radius),y0=std::max(row.y,row.ink_y-radius);
        int x1=std::min(row.x+row.width,row.ink_x+row.ink_width+radius);
        int y1=std::min(row.y+row.height,row.ink_y+row.ink_height+radius);
        auto inRow=[&](int x,int y) {return x>=x0&&x<x1&&y>=y0&&y<y1;};
        struct OutlineColor {
            int samples=0,occupied=0;
            std::array<int,3> sum{};
        };
        std::array<OutlineColor,16> shades{};
        int foregroundPixels=0;

        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x) {
            size_t at=size_t(y)*r.w+x;
            if(core[at]) {++foregroundPixels;continue;}
            if(mask[at]||row.ink_height<12)continue;
            auto p=pixel(x,y);
            int chroma=*std::max_element(p,p+3)-*std::min_element(p,p+3);
            if(chroma>24)continue;
            for(auto const& d:directions) {
                int xx=x+3*d[0],yy=y+3*d[1];
                if(!inRow(xx,yy)||core[size_t(yy)*r.w+xx])continue;
                auto b=pixel(xx,yy);
                // Neutral shadows belong to the glyph when the stroke lies
                // between its core and two consistent exterior samples.
                int fartherX=xx+d[0],fartherY=yy+d[1];
                if(fartherX<row.x||fartherX>=row.x+row.width||fartherY<row.y||fartherY>=row.y+row.height
                   ||core[size_t(fartherY)*r.w+fartherX])continue;
                bool interior=false;
                for(int step=1;step<=radius;++step) {
                    int ix=x-step*d[0],iy=y-step*d[1];
                    if(inRow(ix,iy)&&core[size_t(iy)*r.w+ix]) {interior=true;break;}
                }
                if(!interior)continue;
                auto farther=pixel(fartherX,fartherY);
                int base=luma(b),difference=base-luma(p);
                int foregroundContrast=foregroundLuma-base;
                if(std::abs(base-luma(farther))<=18&&std::abs(difference)>=17&&
                   std::abs(foregroundContrast)>=25&&difference*foregroundContrast>0) {
                    auto& shade=shades[luma(p)/16];
                    ++shade.samples;
                    shade.occupied|=1<<std::min(5,6*(x-x0)/std::max(1,x1-x0));
                    for(int c=0;c<3;++c)shade.sum[c]+=p[c];
                    break;
                }
            }
        }
        // Confirm one recurrent shadow color spanning several glyphs.
        auto shade=std::max_element(shades.begin(),shades.end(),
            [](auto const& a,auto const& b) {return a.samples<b.samples;});
        int zones=0;
        for(int bits=shade->occupied;bits;bits>>=1)zones+=bits&1;
        if(shade->samples<std::max(20,foregroundPixels/10)||zones<3)continue;
        std::array<int,3> color{};
        for(int c=0;c<3;++c)color[c]=shade->sum[c]/shade->samples;
        if(filled.empty())filled.resize(count,0);
        int sampleTop=row.y,sampleBottom=row.y+row.height-1;
        for(int x=x0;x<x1;++x) {
            auto topColor=pixel(x,sampleTop),bottomColor=pixel(x,sampleBottom);
            auto shadeDistance=[&](uint8_t const* p) {
                return std::max({std::abs(int(p[0])-color[0]),std::abs(int(p[1])-color[1]),std::abs(int(p[2])-color[2])});
            };
            bool smooth=sampleBottom>sampleTop &&
                std::max({std::abs(int(topColor[0])-bottomColor[0]),std::abs(int(topColor[1])-bottomColor[1]),
                          std::abs(int(topColor[2])-bottomColor[2])})<=30 &&
                shadeDistance(topColor)>34&&shadeDistance(bottomColor)>34 &&
                distance(topColor)>42&&distance(bottomColor)>42;
            for(int y=y0;y<y1;++y) {
                size_t at=size_t(y)*r.w+x;
                auto p=pixel(x,y);
                std::array<double,3> base{};
                if(smooth)for(int c=0;c<3;++c) {
                    double weight=double(y-sampleTop)/(sampleBottom-sampleTop);
                    base[c]=topColor[c]*(1-weight)+bottomColor[c]*weight;
                }
                if(!mask[at]) {
                    bool fringe=shadeDistance(p)<=18;
                    if(!fringe&&smooth) {
                        double dot=0,norm=0;
                        for(int c=0;c<3;++c) {
                            double v=color[c]-base[c];
                            dot+=(p[c]-base[c])*v;norm+=v*v;
                        }
                        if(norm>=2500) {
                            double alpha=dot/norm,residual=0;
                            for(int c=0;c<3;++c)
                                residual=std::max(residual,std::abs(p[c]-(base[c]+alpha*(color[c]-base[c]))));
                            fringe=alpha>=.16&&alpha<=1.12&&residual<=9;
                        }
                    }
                    if(!fringe)continue;
                    for(int dy=-radius;dy<=radius&&!mask[at];++dy)
                        for(int dx=-radius;dx<=radius;++dx) {
                            int xx=x+dx,yy=y+dy;
                            if(inRow(xx,yy)&&core[size_t(yy)*r.w+xx]) {mask[at]=1;break;}
                        }
                }
                if(mask[at]&&smooth&&!filled[at]) {
                    for(int c=0;c<3;++c)result.pixels[at*4+c]=uint8_t(base[c]+.5);
                    filled[at]=1;
                    ++result.repaired;
                }
            }
        }
        repairedOutline=true;
    }
    for(auto value:mask)result.masked+=value!=0;
    // Fill only masked pixels, from the boundary inward. Choose the opposite
    // sample pair with the smallest color discontinuity: a ring's two sides
    // continue through a narrow glyph rather than blending into its surround.
    auto pending=mask;
    if(!filled.empty())for(size_t at=0;at<count;++at)if(filled[at])pending[at]=0;
    std::vector<uint32_t> queue;queue.reserve(result.masked);
    std::vector<uint8_t> queued(count,0);
    auto enqueue=[&](int x,int y) {
        if(x<0||y<0||x>=r.w||y>=r.h)return;
        size_t at=size_t(y)*r.w+x;if(!pending[at]||queued[at])return;
        bool edge=false;
        for(int i=0;i<4;++i) {
            int xx=x+directions[i][0],yy=y+directions[i][1];
            if(xx>=0&&yy>=0&&xx<r.w&&yy<r.h&&!pending[size_t(yy)*r.w+xx]) {edge=true;break;}
        }
        if(edge) {queued[at]=1;queue.push_back(uint32_t(at));}
    };
    for(int y=0;y<r.h;++y)for(int x=0;x<r.w;++x)enqueue(x,y);
    for(size_t cursor=0;cursor<queue.size();++cursor) {
        size_t at=queue[cursor];int x=int(at%r.w),y=int(at/r.w);
        double best=1e20;std::array<double,3> color{};bool found=false;
        for(int axis=0;axis<4;++axis) {
            int dx=directions[axis*2][0],dy=directions[axis*2][1];
            uint8_t const* samples[2]={nullptr,nullptr};int distances[2]={0,0};
            for(int side=0;side<2;++side)for(int step=1;step<=12;++step) {
                int sign=side?1:-1,xx=x+dx*step*sign,yy=y+dy*step*sign;
                if(xx<0||yy<0||xx>=r.w||yy>=r.h)break;
                if(!pending[size_t(yy)*r.w+xx]) {
                    samples[side]=result.pixels.data()+(size_t(yy)*r.w+xx)*4;distances[side]=step;break;
                }
            }
            if(!samples[0]||!samples[1])continue;
            double score=double(distances[0]+distances[1])*2;
            for(int c=0;c<3;++c)score+=std::abs(int(samples[0][c])-samples[1][c]);
            if(score<best) {
                best=score;found=true;
                for(int c=0;c<3;++c)color[c]=(double(samples[0][c])*distances[1]+double(samples[1][c])*distances[0])/(distances[0]+distances[1]);
            }
        }
        if(!found) {
            int neighbors=0;
            for(auto const& d:directions) {
                int xx=x+d[0],yy=y+d[1];
                if(xx<0||yy<0||xx>=r.w||yy>=r.h||pending[size_t(yy)*r.w+xx])continue;
                auto p=result.pixels.data()+(size_t(yy)*r.w+xx)*4;
                for(int c=0;c<3;++c)color[c]+=p[c];++neighbors;
            }
            if(!neighbors)continue;
            for(auto& c:color)c/=neighbors;
        }
        for(int c=0;c<3;++c)result.pixels[at*4+c]=uint8_t(std::clamp(color[c],0.0,255.0)+.5);
        pending[at]=0;++result.repaired;
        for(int i=0;i<4;++i)enqueue(x+directions[i][0],y+directions[i][1]);
    }
    if(result.repaired!=result.masked) {reject("repair_incomplete");return result;}
    result.reason=repairedOutline?"outlined_glyph_repaired":"glyph_mask_repaired";
    return result;
}
