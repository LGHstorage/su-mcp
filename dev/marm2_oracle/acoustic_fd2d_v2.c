/* 2D acoustic finite-difference modeling of the Marmousi2 reference line.
 * Recording starts at the wavelet peak, with a Cerjan sponge on both time levels.
 * usage: fd vp.bin nx nz dx dt nt_after_onset nb f0 shots.txt nshot out.bin nrec S
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <string.h>
#ifdef _OPENMP
#include <omp.h>
#endif
static void die(const char *m){ fprintf(stderr,"%s\n",m); exit(2); }
int main(int argc,char **argv){
 if(argc!=14){fprintf(stderr,"usage: %s vp.bin nx nz dx dt nt_after_onset nb f0 shots.txt nshot out.bin nrec S\n",argv[0]);return 2;}
 const char *vpfile=argv[1],*shotfile=argv[9],*outfile=argv[11];
 int nx=atoi(argv[2]),nz=atoi(argv[3]),nt=atoi(argv[6]),nb=atoi(argv[7]),nshot=atoi(argv[10]);
 float dx=atof(argv[4]),dt=atof(argv[5]),f0=atof(argv[8]);
 const int rec_step=2,near_cells=20,src_z_phys=2,rec_z_phys=1,decim=2;
 int nrec=atoi(argv[12]); float S=atof(argv[13]); int onset=(int)lrintf(1.5f/f0/dt); int nrec_steps=nt; nt=onset+nrec_steps;
 if(nrec<1 || nrec>nx || nt<3 || nshot<1)die("invalid count");
 int ntout=(nrec_steps-1)/decim+1,NX=nx+2*nb,NZ=nz+2*nb; size_t N=(size_t)NX*NZ;
 float *vp=malloc((size_t)nx*nz*4),*vpp=malloc(N*4),*p0=calloc(N,4),*p1=calloc(N,4),*p2=calloc(N,4),*damp=malloc(N*4),*recbuf=malloc((size_t)nrec*ntout*4);
 if(!vp||!vpp||!p0||!p1||!p2||!damp||!recbuf) die("allocation failed");
 FILE *f=fopen(vpfile,"rb");if(!f)die("vp open failed");if(fread(vp,4,(size_t)nx*nz,f)!=(size_t)nx*nz)die("vp read failed");fclose(f);
 #pragma omp parallel for collapse(2) schedule(static)
 for(int iz=0;iz<NZ;iz++)for(int ix=0;ix<NX;ix++){int jx=ix-nb;if(jx<0)jx=0;if(jx>=nx)jx=nx-1;int jz=iz-nb;if(jz<0)jz=0;if(jz>=nz)jz=nz-1;vpp[(size_t)iz*NX+ix]=vp[(size_t)jz*nx+jx];}
 #pragma omp parallel for collapse(2) schedule(static)
 for(int iz=0;iz<NZ;iz++)for(int ix=0;ix<NX;ix++){int d=ix;if(NX-1-ix<d)d=NX-1-ix;if(iz<d)d=iz;if(NZ-1-iz<d)d=NZ-1-iz;float q=d<nb?(float)(nb-d)/(float)nb:0.0f;damp[(size_t)iz*NX+ix]=expf(-S*q*q);}
 int *sx=malloc((size_t)nshot*sizeof(int));f=fopen(shotfile,"r");if(!f)die("shots open failed");for(int i=0;i<nshot;i++)if(fscanf(f,"%d",&sx[i])!=1)die("shots parse failed");fclose(f);
 FILE *fo=fopen(outfile,"wb");if(!fo)die("out open failed");
 const float c0=-205.0f/72.0f,c1=8.0f/5.0f,c2=-1.0f/5.0f,c3=8.0f/315.0f,c4=-1.0f/560.0f,idx2=1.0f/(dx*dx),dt2=dt*dt,pi=3.14159265358979323846f,t0=1.5f/f0;
 for(int is=0;is<nshot;is++){
  memset(p0,0,N*4);memset(p1,0,N*4);memset(p2,0,N*4);memset(recbuf,0,(size_t)nrec*ntout*4);
  int sxi=nb+sx[is],szi=nb+src_z_phys,rzi=nb+rec_z_phys,outi=0;
  if(sx[is]-near_cells-(nrec-1)*rec_step<0 || sx[is]>=nx)die("receiver or source outside physical model");
  #pragma omp parallel shared(p0,p1,p2,outi)
  {
   for(int it=0;it<nt;it++){
    #pragma omp for schedule(static)
    for(int iz=4;iz<NZ-4;iz++){
     size_t row=(size_t)iz*NX;
     #pragma omp simd
     for(int ix=4;ix<NX-4;ix++){
      size_t k=row+ix;float pc=p1[k];
      float dxx=(c0*pc+c1*(p1[k-1]+p1[k+1])+c2*(p1[k-2]+p1[k+2])+c3*(p1[k-3]+p1[k+3])+c4*(p1[k-4]+p1[k+4]))*idx2;
      float dzz=(c0*pc+c1*(p1[k-NX]+p1[k+NX])+c2*(p1[k-2*NX]+p1[k+2*NX])+c3*(p1[k-3*NX]+p1[k+3*NX])+c4*(p1[k-4*NX]+p1[k+4*NX]))*idx2;
      float vv=vpp[k];p2[k]=((2.0f*pc-p0[k])+dt2*vv*vv*(dxx+dzz))*damp[k];
     }
    }
    /* Cerjan: damp the previous field as well as the new one */
    #pragma omp for schedule(static)
    for(size_t k=0;k<N;k++) p1[k]*=damp[k];
    #pragma omp single
    {
     float t=it*dt,a=pi*f0*(t-t0),w=(1.0f-2.0f*a*a)*expf(-a*a);p2[(size_t)szi*NX+sxi]+=w;
     if(it>=onset && ((it-onset)%decim)==0 && outi<ntout){for(int ir=0;ir<nrec;ir++){int rxi=sxi-near_cells-ir*rec_step;recbuf[(size_t)ir*ntout+outi]=p2[(size_t)rzi*NX+rxi];}outi++;}
     float *tmp=p0;p0=p1;p1=p2;p2=tmp;
    }
   }
  }
  if(fwrite(recbuf,4,(size_t)nrec*ntout,fo)!=(size_t)nrec*ntout)die("write failed");fprintf(stderr,"shot %d/%d sx_index=%d done\n",is+1,nshot,sx[is]);fflush(stderr);
 }
 fclose(fo);free(vp);free(vpp);free(p0);free(p1);free(p2);free(damp);free(recbuf);free(sx);return 0;
}
