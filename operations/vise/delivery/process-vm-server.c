/* Synthetic health service for process/control qualification only. */
#include <sys/socket.h>
#include <netinet/in.h>
#include <signal.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
static volatile sig_atomic_t stop_requested=0;
static void stop(int signal_number){(void)signal_number;stop_requested=1;}
int main(void){
  struct sigaction action={0};action.sa_handler=stop;sigemptyset(&action.sa_mask);
  sigaction(SIGTERM,&action,0);sigaction(SIGINT,&action,0);signal(SIGPIPE,SIG_IGN);
  int socket_fd=socket(AF_INET,SOCK_STREAM,0),yes=1;
  if(socket_fd<0)return 2;
  setsockopt(socket_fd,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
  struct sockaddr_in address={0};address.sin_family=AF_INET;
  address.sin_port=htons(3017);address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
  if(bind(socket_fd,(struct sockaddr *)&address,sizeof(address))||listen(socket_fd,8))return 3;
  const char reply[]="HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{\"status\":\"ok\",\"prototype\":true}";
  while(!stop_requested){
    int client=accept(socket_fd,0,0);
    if(client<0){if(errno==EINTR)continue;return 4;}
    char request[1024];ssize_t received=read(client,request,sizeof(request));
    if(received>0){
      size_t offset=0;
      while(offset<strlen(reply)){
        ssize_t sent=write(client,reply+offset,strlen(reply)-offset);
        if(sent<0 && errno==EINTR)continue;
        if(sent<=0)break;
        offset+=(size_t)sent;
      }
    }
    close(client);
  }
  close(socket_fd);return 0;
}
