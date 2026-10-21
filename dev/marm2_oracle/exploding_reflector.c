/* Exploding-reflector zero-offset reference section for the Marmousi2 line.
 * usage: er vp_half.bin refl.bin nx nz dx dt nt nb f0 rec_z_cells rec_step decim out.bin
 */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
static void die(const char *m){ fprintf(stderr,"%s\n",m); exit(2); }
int main(int argc,char **argv){
 if(argc!=14)die("usage: er vp_half.bin refl.bin nx nz dx dt nt nb f0 rec_z_cells rec_step decim out.bin");
 int nx=atoi(argv[3]),nz=atoi(argv[4]),nt=atoi(argv[7]),nb=atoi(argv[8]);
 float dx=atof(argv[5]),dt=atof(argv[6]),f0=atof(argv[9]);
 int rzc=atoi(argv[10]),rstep=atoi(argv[11]),decim=atoi(argv[12]);
 int NX=nx+2*nb,NZ=nz+2*nb,nrec=(nx-1)/rstep+1,ntout=(nt-1)/decim+1; size_t N=(size_t)NX*NZ;
 float *vp=malloc((size_t)nx*nz*4),*rf=malloc((size_t)nx*nz*4),*vpp=malloc(N*4),*rr=calloc(N,4),
       *p0=calloc(N,4),*p1=calloc(N,4),*p2=calloc(N,4),*damp=malloc(N*4),*rec=calloc((size_t)nrec*ntout,4);
 if(!vp||!rf||!vpp||!rr||!p0||!p1||!p2||!damp||!rec)die("allocation failed");
 FILE *f=fopen(argv[1],"rb");if(!f||fread(vp,4,(size_t)nx*nz,f)!=(size_t)nx*nz)die("vp read");fclose(f);
 f=fopen(argv[2],"rb");if(!f||fread(rf,4,(size_t)nx*nz,f)!=(size_t)nx*nz)die("refl read");fclose(f);
 for(int iz=0;iz<NZ;iz++)for(int ix=0;ix<NX;ix++){int jx=ix-nb;if(jx<0)jx=0;if(jx>=nx)jx=nx-1;int jz=iz-nb;if(jz<0)jz=0;if(jz>=nz)jz=nz-1;
   vpp[(size_t)iz*NX+ix]=vp[(size_t)jz*nx+jx];
   if(ix>=nb&&ix<nb+nx&&iz>=nb&&iz<nb+nz)rr[(size_t)iz*NX+ix]=rf[(size_t)(iz-nb)*nx+(ix-nb)];}
 const float strength=4.0f;
 for(int iz=0;iz<NZ;iz++)for(int ix=0;ix<NX;ix++){int d=ix;if(NX-1-ix<d)d=NX-1-ix;if(iz<d)d=iz;if(NZ-1-iz<d)d=NZ-1-iz;float q=d<nb?(float)(nb-d)/(float)nb:0.0f;damp[(size_t)iz*NX+ix]=expf(-strength*q*q*dt);}
 const float c0=-205.0f/72.0f,c1=8.0f/5.0f,c2=-1.0f/5.0f,c3=8.0f/315.0f,c4=-1.0f/560.0f,idx2=1.0f/(dx*dx),dt2=dt*dt,pi=3.14159265358979323846f,t0=1.5f/f0;
 int outi=0;
 for(int it=0;it<nt;it++){
  float t=it*dt,a=pi*f0*(t-t0),w=(1.0f-2.0f*a*a)*expf(-a*a);
  #pragma omp parallel for schedule(static)
  for(int iz=4;iz<NZ-4;iz++){size_t row=(size_t)iz*NX;
   for(int ix=4;ix<NX-4;ix++){size_t k=row+ix;float pc=p1[k];
    float dxx=(c0*pc+c1*(p1[k-1]+p1[k+1])+c2*(p1[k-2]+p1[k+2])+c3*(p1[k-3]+p1[k+3])+c4*(p1[k-4]+p1[k+4]))*idx2;
    float dzz=(c0*pc+c1*(p1[k-NX]+p1[k+NX])+c2*(p1[k-2*NX]+p1[k+2*NX])+c3*(p1[k-3*NX]+p1[k+3*NX])+c4*(p1[k-4*NX]+p1[k+4*NX]))*idx2;
    float vv=vpp[k];p2[k]=((2.0f*pc-p0[k])+dt2*vv*vv*(dxx+dzz))*damp[k]+w*rr[k];}}
  if((it%decim)==0){for(int ir=0;ir<nrec;ir++)rec[(size_t)ir*ntout+outi]=p2[(size_t)(nb+rzc)*NX+nb+ir*rstep];outi++;}
  float *tmp=p0;p0=p1;p1=p2;p2=tmp;
 }
 f=fopen(argv[13],"wb");if(!f||fwrite(rec,4,(size_t)nrec*ntout,f)!=(size_t)nrec*ntout)die("write");fclose(f);
 fprintf(stderr,"er done nrec=%d ntout=%d\n",nrec,ntout);return 0;
}
